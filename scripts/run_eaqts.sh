#!/usr/bin/env bash

# ------------------------------------------------------------
# Single‑script starter for EAQTS V2.4 on Windows (git‑bash/MSYS).
# It performs the minimal set‑up and launches the autonomous
# trading loop in the background.
# ------------------------------------------------------------

set -euo pipefail

# Helper to print info messages
info() { echo -e "[INFO] $*"; }
error() { echo -e "[ERROR] $*" >&2; }

# ------------------------------------------------------------
# 1. Ensure Scoop is installed (Windows package manager)
# ------------------------------------------------------------
if ! command -v scoop >/dev/null 2>&1; then
    info "Installing Scoop..."
    powershell -Command "iwr -useb get.scoop.sh | iex"
    # Add the extras bucket for optional services (PostgreSQL, Redis, …)
    scoop bucket add extras
else
    info "Scoop already installed"
fi

# ------------------------------------------------------------
# 2. Install core tools (Python 3.11+ and Poetry) if missing
# ------------------------------------------------------------
if ! command -v python >/dev/null 2>&1; then
    info "Installing Python via Scoop..."
    scoop install python
else
    info "Python already present"
fi

if ! command -v poetry >/dev/null 2>&1; then
    info "Installing Poetry via Scoop..."
    scoop install poetry
else
    info "Poetry already present"
fi

# ------------------------------------------------------------
# 3. (Optional) Install production services – uncomment if required
# ------------------------------------------------------------
# if ! command -v psql >/dev/null 2>&1; then
#     info "Installing PostgreSQL via Scoop..."
#     scoop install postgresql
# fi
# if ! command -v redis-server >/dev/null 2>&1; then
#     info "Installing Redis via Scoop..."
#     scoop install redis
# fi
# if ! command -v influxd >/dev/null 2>&1; then
#     info "Installing InfluxDB via Scoop..."
#     scoop install influxdb
# fi
# if ! command -v nats-server >/dev/null 2>&1; then
#     info "Installing NATS Server via Scoop..."
#     scoop install nats-server
# fi
# if ! command -v prometheus >/dev/null 2>&1; then
#     info "Installing Prometheus via Scoop..."
#     scoop install prometheus
# fi
# if ! command -v grafana-server >/dev/null 2>&1; then
#     info "Installing Grafana via Scoop..."
#     scoop install grafana
# fi

# ------------------------------------------------------------
# 4. Move to project root (assumes script lives in /scripts)
# ------------------------------------------------------------
cd "$(dirname "$0")/.."

# ------------------------------------------------------------
# 5. Install all Python dependencies (including dev/ML/vis/trading extras)
# ------------------------------------------------------------
info "Installing Python dependencies via Poetry..."
poetry install --with dev,ml,viz,trading

# ------------------------------------------------------------
# 6. Prepare runtime configuration (.env) if not present
# ------------------------------------------------------------
if [ ! -f .env ]; then
    info "Creating .env from .env.example"
    cp .env.example .env
    echo "# Edit .env with your MT5, exchange API keys, and DB URLs" >> .env
fi

# ------------------------------------------------------------
# 7. Initialise the system (creates DB, starts Prometheus exporter, runs a quick test)
# ------------------------------------------------------------
info "Running eaqts-cli init..."
poetry run python scripts/eaqts_cli.py init

# ------------------------------------------------------------
# 8. Start the autonomous trading loop (background, PID stored)
# ------------------------------------------------------------
info "Starting the EAQTS trading loop..."
poetry run python scripts/eaqts_cli.py start

info "EAQTS is now running. Use 'eaqts-cli status' or 'eaqts-cli stop' to manage it."
