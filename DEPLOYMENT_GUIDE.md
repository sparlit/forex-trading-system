# Forex Trading System - Deployment Guide

## Table of Contents
1. [System Overview](#system-overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Detailed Installation](#detailed-installation)
5. [Configuration](#configuration)
6. [Deployment Options](#deployment-options)
7. [Monitoring & Maintenance](#monitoring--maintenance)
8. [Troubleshooting](#troubleshooting)
8. [Security Considerations](#security-considerations)

---

## System Overview

The Forex Trading System is a fully autonomous, AI-powered trading platform that:

- **Collects** real-time market data from MT5 (Forex/Metals) and CCXT (Crypto)
- **Analyzes** markets using 15+ trading strategies (7 styles + 8 ML models)
- **Predicts** next-candle movements with ensemble ML models
- **Executes** trades with advanced risk management
- **Monitors** blind spots and regime changes continuously
- **Visualizes** everything in a 12-tab real-time dashboard

### Architecture Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **API Server** | FastAPI + Uvicorn | REST API, WebSocket, Signal distribution |
| **Dashboard** | Streamlit + Plotly | 12-tab real-time monitoring |
| **Strategy Engine** | 15 strategies | Signal generation across 7 styles |
| **Risk Manager** | Portfolio risk, VaR, CVaR | Position sizing, circuit breakers |
| **Execution Engine** | Multi-broker, smart routing | Order management, algorithms |
| **Data Ingestion** | MT5 + CCXT + REST | Real-time market data |
| **MT5 EA Bridge** | MQL5 + ZeroMQ/HTTP | Real-time MT5 data feed |
| **Database** | TimescaleDB + Redis | Time-series + caching |
| **Message Bus** | NATS + JetStream | Event-driven architecture |
| **Monitoring** | Prometheus + Grafana | Metrics, alerting, dashboards |

---

## Prerequisites

### Required Software
| Software | Version | Purpose |
|----------|---------|---------|
| **Windows** | 10/11 Pro | Host OS |
| **Docker Desktop** | 4.25+ | Container orchestration |
| **WSL 2** | Latest | Docker backend |
| **MetaTrader 5** | Build 4000+ | Forex/Metals data & execution |
| **Python** | 3.11+ | Development/debugging |
| **Git** | Latest | Version control |

### Hardware Requirements
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 4 cores | 8+ cores |
| **RAM** | 16 GB | 32 GB |
| **Storage** | 100 GB SSD | 500 GB NVMe |
| **Network** | 10 Mbps | 100+ Mbps low latency |

### MT5 Account Requirements
- Demo or Live account with hedging enabled
- API access enabled in MT5 (Tools -> Options -> Expert Advisors)
- Allow DLL imports and WebRequest for listed URLs
- Symbols: EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD, ETHUSD (minimum)

---

## Quick Start (5 Minutes)

```powershell
# 1. Clone repository
git clone https://github.com/your-repo/forex-trading-system.git
cd forex-trading-system

# 2. Run master installer (as Administrator)
.\INSTALL.bat

# 3. Edit .env with your credentials
notepad .env

# 4. Start the system
.\start_trading_system.ps1

# 5. Choose option A for full system
# Access dashboard at http://localhost:8501
```

---

## Detailed Installation

### Step 1: System Preparation

```powershell
# Enable WSL2 (required for Docker)
wsl --install
wsl --set-default-version 2
# Restart computer

# Install Docker Desktop
# Download from: https://www.docker.com/products/docker-desktop/
# Enable "Use WSL 2 based engine" in Docker Desktop settings

# Verify installation
docker version
docker compose version
```

### Step 2: Repository Setup

```powershell
git clone https://github.com/your-org/forex-trading-system.git
cd forex-trading-system

# Run master installer (creates .env, builds images, starts DB)
.\INSTALL.bat
```

### Step 3: Configure Credentials

Edit `.env` with your actual values:

```ini
# Critical - MUST CHANGE
TIMESCALE_PASSWORD=your_secure_db_password
INFLUX_PASSWORD=your_influx_password
INFLUX_TOKEN=your_super_secret_token
SECRET_KEY=your_64_char_random_string
JWT_EXPIRATION_MINUTES=60

# MT5 (Required for live trading)
MT5_ENABLED=true
MT5_LOGIN=12345678
MT5_PASSWORD=your_mt5_password
MT5_SERVER=YourBroker-Demo
MT5_PATH=C:\Program Files\MetaTrader 5	erminal64.exe

# API Keys (Optional - for enhanced data)
CCXT_API_KEYS={"binance": {"apiKey": "xxx", "secret": "yyy"}}
TWELVE_DATA_API_KEY=your_key
FINNHUB_API_KEY=your_key

# Risk Settings (Adjust for your risk tolerance)
RISK_MAX_PORTFOLIO_RISK=0.02
RISK_MAX_DRAWDOWN=0.10
RISK_DAILY_LOSS_LIMIT=0.05
```

### Step 4: MT5 EA Installation

1. Open `ea/ForexTradingSystemEA.mq5` in MetaEditor (F4 in MT5)
2. Compile (F7) - ensure no errors
3. In MT5: Tools -> Options -> Expert Advisors
   - Allow automated trading
   - Allow DLL imports
   - Allow WebRequest for: `http://localhost:8000`, `ws://localhost:5555`
3. Add EA to chart (any timeframe, any allowed symbol)
4. Configure inputs:
   - `PythonHost`: `127.0.0.1`
   - `UseZeroMQ`: `true` (for lowest latency)
   - `EnableNewsFeed`: `true`
   - `EnableBracketOrders`: `true`
   - `RiskPerTrade`: `0.02`

---

## Configuration

### Environment Variables (.env)

| Variable | Description | Required |
|----------|-------------|----------|
| `TIMESCALE_PASSWORD` | PostgreSQL password | Yes |
| `INFLUX_PASSWORD` | InfluxDB admin password | Yes |
| `INFLUX_TOKEN` | InfluxDB admin token | Yes |
| `SECRET_KEY` | JWT signing key (64 chars) | Yes |
| `MT5_LOGIN` | MT5 account number | For live trading |
| `MT5_PASSWORD` | MT5 master password | For live trading |
| `MT5_SERVER` | Broker server name | For live trading |
| `CCXT_API_KEYS` | JSON with exchange keys | For crypto |
| `SIMULATION_MODE` | `false` for demo/live | No (default: false) |

### Risk Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `RISK_MAX_PORTFOLIO_RISK` | 0.02 | Max 2% portfolio risk per trade |
| `RISK_MAX_DRAWDOWN` | 0.10 | Stop trading at 10% drawdown |
| `RISK_DAILY_LOSS_LIMIT` | 0.05 | Stop at 5% daily loss |
| `RISK_MAX_POSITION_SIZE_PCT` | 0.10 | Max 10% per position |
| `RISK_MAX_LEVERAGE` | 10.0 | Max 10:1 leverage |

### Strategy Weights (Advanced)

```ini
# In .env or strategy config
STRATEGY_ENSEMBLE_METHOD=weighted_average
STRATEGY_MIN_CONFIDENCE=0.6
STRATEGY_MAX_CONCURRENT_SIGNALS=10
```

---

## Deployment Options

### Option 1: Development (Local)

```powershell
# Full system in separate windows
.\start_trading_system.ps1
# Choose A for all components

# Or individual components:
poetry run python -m src.data.runner      # Data worker
poetry run uvicorn src.api.main:app --host 0.0.0.0 --port 8000  # API
poetry run streamlit run src/portfolio/dashboard/app.py  # Dashboard
```

### Option 2: Docker Compose (Production)

```bash
# Development
docker compose -p forex up -d

# Production
docker compose -f docker-compose.yml -f docker-compose.prod.yml -p forex up -d

# Scale workers
docker compose -p forex up -d --scale worker-strategy=4

# View logs
docker compose -p forex logs -f api
docker compose -p forex logs -f worker-strategy
```

### Option 3: Kubernetes (Production Scale)

```yaml
# k8s/forex-trading.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: forex-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: forex-api
  template:
    spec:
      containers:
      - name: api
        image: forex-trading-system:latest
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: forex-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: forex-api
spec:
  ports:
  - port: 8000
  selector:
    app: forex-api
```

### Option 4: Windows Services (Auto-start)

```powershell
# Install as Windows Services
.\install-services.ps1

# Manage services
Start-Service forex-api, forex-dashboard, forex-worker-*
Stop-Service forex-*
Get-Service forex-*
```

---

## Monitoring & Maintenance

### Health Checks

```bash
# System health
curl http://localhost:8000/health

# Database
docker exec forex-timescaledb pg_isready -U trader -d market_data

# Redis
docker exec forex-redis redis-cli ping

# NATS
docker exec forex-nats nats server check jetstream

# API metrics
curl http://localhost:8000/metrics
```

### Dashboard Access

| Service | URL | Credentials |
|---------|-----|-------------|
| **Dashboard** | http://localhost:8501 | - |
| **API Docs** | http://localhost:8000/docs | - |
| **API Health** | http://localhost:8000/health | - |
| **Prometheus** | http://localhost:9090 | - |
| **Grafana** | http://localhost:3000 | admin / admin |
| **NATS Monitor** | http://localhost:8222 | - |
| **InfluxDB** | http://localhost:8086 | admin / token |

### Key Dashboard Tabs

1. **Sessions & Symbols** - Session countdown, overlap timeline, active symbols
2. **Blind Spots** - Correlation alerts, regime changes, model degradation
3. **Brain & Strategies** - Active strategies, decisions, regime
4. **Model Health** - Prediction accuracy, degradation, retrain triggers

---

## Maintenance

### Daily
- Check dashboard for alerts (Blind Spots tab)
- Verify MT5 EA connection (green heartbeat in dashboard)
- Review daily P&L and risk metrics

### Weekly
```bash
# Update Docker images
docker compose -p forex pull
docker compose -p forex up -d --build

# Database maintenance
docker exec forex-timescaledb psql -U trader -d market_data -c "VACUUM ANALYZE;"

# Clean old logs
find logs -name "*.log" -mtime +30 -delete
```

### Monthly
- Rotate secrets (SECRET_KEY, API keys, DB passwords)
- Review strategy performance (Performance tab)
- Check model degradation (Model Health tab)
- Update Docker base images

### Backup

```bash
# Database backup
docker exec forex-timescaledb pg_dump -U trader market_data | gzip > backup_$(date +%Y%m%d).sql.gz

# Configuration backup
tar -czf config_backup_$(date +%Y%m%d).tar.gz .env config/

# Model backup
tar -czf models_backup_$(date +%Y%m%d).tar.gz models/
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **Docker build fails** | Missing dependencies | Run `.\INSTALL.bat` as Admin |
| **MT5 EA won't connect** | Firewall/URL not allowed | Add `http://localhost:8000` to MT5 WebRequest list |
| **No market data** | MT5 not logged in | Login to MT5, enable auto-trading |
| **Dashboard empty** | API not running | Check `docker logs forex-api` |
| **High memory** | Too many workers | Reduce replicas in docker-compose |
| **Model not loading** | Missing model files | Run `poetry run python -m src.strategy.ml.auto_retrain` |

### Logs & Debugging

```bash
# Application logs
docker compose -p forex logs -f --tail=100 api
docker compose -p forex logs -f --tail=100 worker-strategy

# MT5 EA logs
# In MT5: View -> Terminal -> Experts tab

# Database queries
docker exec -i forex-timescaledb psql -U trader -d market_data -c "
SELECT s.symbol, COUNT(*) as bars, MAX(b.timestamp) as last_bar
FROM market_data.bars b
JOIN market_data.symbols s ON b.symbol_id = s.symbol_id
WHERE b.is_complete = TRUE
GROUP BY s.symbol
ORDER BY last_bar DESC;"
```

### Performance Tuning

| Parameter | Default | High-Freq | Low-Latency |
|-----------|---------|-----------|-------------|
| `DataFrequency` (EA) | 1 | 1 | 1 |
| `HeartbeatInterval` | 5s | 3s | 1s |
| `API_WORKERS` | 1 | 4 | 8 |
| `Strategy workers` | 2 | 4 | 8 |
| `Redis maxmemory` | 512MB | 1GB | 2GB |

---

## Security Considerations

### Network Security
- **Never expose ports directly to internet**
- Use VPN/SSH tunnel for remote dashboard access
- Configure firewall: only localhost for 8000, 8501, 9090, 3000

### Credential Management
```bash
# Use Docker secrets in production
echo "your_password" | docker secret create timescale_password -

# In docker-compose.prod.yml:
secrets:
  timescale_password:
    external: true
services:
  timescaledb:
    secrets:
      - timescale_password
environment:
  POSTGRES_PASSWORD_FILE: /run/secrets/timescale_password
```

### API Security
- Enable JWT authentication in production
- Configure CORS origins explicitly
- Use HTTPS with valid certificates
- Rate limit API endpoints

### MT5 Security
- Use dedicated demo account for testing
- Enable 2FA on broker account
- Set IP restrictions in broker portal
- Monitor for unauthorized EA attachments

---

## Quick Reference

### Essential Commands

```powershell
# Full start
.\start_trading_system.ps1
# Choose A

# Stop everything
docker compose -p forex down

# Restart single service
docker compose -p forex restart api

# View logs
docker compose -p forex logs -f --tail=100 api

# Database shell
docker exec -it forex-timescaledb psql -U trader -d market_data

# Redis CLI
docker exec -it forex-redis redis-cli

# Update system
git pull
.\INSTALL.bat
docker compose -p forex up -d --build
```

### Key Files

| File | Purpose |
|------|---------|
| `.env` | All configuration |
| `docker-compose.yml` | Development stack |
| `docker-compose.prod.yml` | Production overrides |
| `INSTALL.bat` | Master installer |
| `start_trading_system.ps1` | Component launcher |
| `scripts/init-timescaledb.sql` | Database schema |
| `ea/ForexTradingSystemEA.mq5` | MT5 Expert Advisor |
| `src/strategy/autonomous/brain.py` | Main trading brain |
| `src/portfolio/dashboard/app.py` | Streamlit dashboard |

---

## Support

### Resources
- **Architecture**: `ARCHITECTURE.md`
- **Technical Docs**: `TECHNICAL_DOCUMENTATION.md`
- **API Docs**: http://localhost:8000/docs
- **Issues**: GitHub Issues

### Emergency Procedures

```powershell
# EMERGENCY STOP - Kill all trading
docker compose -p forex kill
docker compose -p forex down

# Close all MT5 positions manually
# In MT5: Right-click positions -> Close All
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0.0 | 2024 | Complete rewrite with ML, session mgmt, blind spots |
| 1.5.0 | 2023 | Added ML strategies, risk management |
| 1.0.0 | 2022 | Initial release |

---

*Documentation generated for Forex Trading System v2.0.0*
*Last updated: 2024*

---

**Disclaimer**: This software is for educational and research purposes. Trading financial instruments carries substantial risk. Never trade with money you cannot afford to lose. Always test thoroughly on demo accounts before live deployment.
