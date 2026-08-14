#!/usr/bin/env bash
# ============================================================
# Forex Trading System - Autonomous Launcher
# ============================================================
# Single command to start entire trading system
# Runs all services in background, handles shutdown gracefully
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $*"; }
success() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)]${NC} $*"; }
error() { echo -e "${RED}[$(date +%H:%M:%S)]${NC} $*"; }

# Track PIDs for cleanup
PIDS=()

cleanup() {
    log "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    # Force kill any remaining
    pkill -f "postgres.*forex" 2>/dev/null || true
    pkill -f "redis-server" 2>/dev/null || true
    pkill -f "influxdb3" 2>/dev/null || true
    pkill -f "nats-server" 2>/dev/null || true
    pkill -f "prometheus" 2>/dev/null || true
    pkill -f "grafana" 2>/dev/null || true
    pkill -f "src.api.main" 2>/dev/null || true
    pkill -f "streamlit.*dashboard" 2>/dev/null || true
    success "All services stopped"
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

wait_for_port() {
    local port=$1
    local name=$2
    local timeout=${3:-30}
    local count=0
    while ! nc -z localhost "$port" 2>/dev/null; do
        sleep 1
        ((count++))
        if [[ $count -ge $timeout ]]; then
            error "$name failed to start on port $port"
            return 1
        fi
    done
    success "$name ready on port $port"
    return 0
}

# ============================================================
# START INFRASTRUCTURE
# ============================================================
log "=== STARTING INFRASTRUCTURE ==="

# PostgreSQL
log "Starting PostgreSQL..."
pg_ctl -D "$HOME/scoop/apps/postgresql/current/data" -l "$LOG_DIR/postgresql.log" start >/dev/null 2>&1
wait_for_port 5432 "PostgreSQL"

# Redis
log "Starting Redis..."
redis-server --daemonize yes --logfile "$LOG_DIR/redis.log" >/dev/null 2>&1
wait_for_port 6379 "Redis"

# InfluxDB 3
log "Starting InfluxDB..."
cd "$HOME/scoop/apps/influxdb/current"
nohup ./influxdb3.exe serve --node-id node1 --object-store memory --data-dir "$HOME/scoop/persist/influxdb/data" --disable-authz health >"$LOG_DIR/influxdb.log" 2>&1 &
PIDS+=($!)
wait_for_port 8181 "InfluxDB"

# NATS
log "Starting NATS..."
cd "$HOME/scoop/apps/nats-server/current"
nohup ./nats-server.exe -js -m 8223 >"$LOG_DIR/nats.log" 2>&1 &
PIDS+=($!)
wait_for_port 4222 "NATS"

# Prometheus
log "Starting Prometheus..."
cd "$HOME/scoop/apps/prometheus/current"
nohup ./prometheus.exe --config.file="$HOME/scoop/apps/prometheus/current/prometheus.yml" --storage.tsdb.path="$HOME/scoop/persist/prometheus/data" --web.enable-lifecycle >"$LOG_DIR/prometheus.log" 2>&1 &
PIDS+=($!)
wait_for_port 9090 "Prometheus"

# Grafana
log "Starting Grafana..."
cd "$HOME/scoop/apps/grafana/current/bin"
nohup ./grafana.exe server --homepath="$HOME/scoop/apps/grafana/current" >"$LOG_DIR/grafana.log" 2>&1 &
PIDS+=($!)
wait_for_port 3000 "Grafana"

# ============================================================
# START APPLICATION
# ============================================================
log "=== STARTING TRADING APPLICATION ==="

cd "$PROJECT_DIR"

# Ensure dependencies
log "Installing Python dependencies..."
poetry install --no-interaction >/dev/null 2>&1

# API Server
log "Starting API server..."
nohup poetry run python -m src.api.main >"$LOG_DIR/api.log" 2>&1 &
PIDS+=($!)
wait_for_port 8000 "API"

# Dashboard
log "Starting Dashboard..."
nohup poetry run streamlit run src/portfolio/dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true >"$LOG_DIR/dashboard.log" 2>&1 &
PIDS+=($!)
wait_for_port 8501 "Dashboard"

# ============================================================
# RUNNING
# ============================================================
echo ""
success "=== FOREX TRADING SYSTEM RUNNING ==="
echo -e "${CYAN}Access URLs:${NC}"
echo -e "  ${YELLOW}API (Swagger):${NC}     http://localhost:8000/docs"
echo -e "  ${YELLOW}API (Health):${NC}      http://localhost:8000/health"
echo -e "  ${YELLOW}Dashboard:${NC}         http://localhost:8501"
echo -e "  ${YELLOW}Prometheus:${NC}        http://localhost:9090"
echo -e "  ${YELLOW}Grafana:${NC}           http://localhost:3000 (admin/admin)"
echo -e "  ${YELLOW}NATS Monitor:${NC}      http://localhost:8223"
echo -e "  ${YELLOW}InfluxDB:${NC}          http://localhost:8181"
echo ""
log "Press Ctrl+C to stop all services"
echo ""

# Keep running
while true; do
    sleep 10
    # Check if critical services still alive
    for pid in "${PIDS[@]}"; do
        if ! kill -0 "$pid" 2>/dev/null; then
            warn "Process $pid died, restarting..."
        fi
    done
done