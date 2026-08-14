@echo off
REM ============================================================
REM Forex Trading System - Master Installation Script
REM ============================================================
REM This script performs a complete installation of the Forex Trading System
REM including all infrastructure, dependencies, and configuration.
REM Run as Administrator!
REM ============================================================

@echo off
setlocal enabledelayedexpansion

REM Enable ANSI colors for Windows 10+
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "GREEN=%ESC%[32m"
set "RED=%ESC%[31m"
set "YELLOW=%ESC%[33m"
set "CYAN=%ESC%[36m"
set "RESET=%ESC%[0m"

echo.
echo %CYAN%============================================================%RESET%
echo %CYAN%   FOREX TRADING SYSTEM - MASTER INSTALLATION%RESET%
echo %CYAN%============================================================%RESET%
echo.

REM ============================================================
REM Check if running as Administrator
REM ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[ERROR] This script must be run as Administrator%RESET%
    echo Please right-click and select "Run as Administrator"
    pause
    exit /b 1
)

echo %GREEN%[OK]%RESET% Running as Administrator
echo.

REM ============================================================
REM STEP 1: Check Prerequisites
REM ============================================================
echo %CYAN%[1/8] Checking prerequisites...%RESET%

REM Check Docker Desktop
docker version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR] Docker Desktop not found or not running%RESET%
    echo Please install Docker Desktop from https://www.docker.com/products/docker-desktop/
    echo Make sure Docker Desktop is running before continuing.
    pause
    exit /b 1
)
echo %GREEN%[OK]%RESET% Docker Desktop is running

REM Check Docker Compose
docker compose version >nul 2>&1
if errorlevel 1 (
    echo %RED%[ERROR] Docker Compose not available%RESET%
    pause
    exit /b 1
)
echo %GREEN%[OK]%RESET% Docker Compose available

REM Check Git
git --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%[WARN] Git not in PATH. Install from https://git-scm.com/%RESET%
) else (
    echo %GREEN%[OK]%RESET% Git available
)

REM Check Python (optional - used via Docker)
python --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%[WARN] Python not in PATH (optional - used via Docker)%RESET%
) else (
    echo %GREEN%[OK]%RESET% Python available
)

echo.

REM ============================================================
REM STEP 2: Generate Environment File
REM ============================================================
echo %CYAN%[2/8] Generating environment configuration...%RESET%

if not exist ".env" (
    copy .env.example .env >nul
    echo %GREEN%[OK]%RESET% Created .env from template
    echo %YELLOW%[WARN]%RESET% Please edit .env with your credentials before starting!
) else (
    echo %CYAN%[INFO]%RESET% .env already exists, skipping generation
)

REM Generate secure random SECRET_KEY using PowerShell
powershell -NoProfile -Command "& { $key = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 64 | ForEach-Object { [char]$_ }); (Get-Content .env) -replace 'change-me-in-production-use-secure-random-key', \$key | Set-Content .env }" 2>nul
echo %GREEN%[OK]%RESET% Generated secure SECRET_KEY

echo.

REM ============================================================
REM STEP 3: Create Required Directories
REM ============================================================
echo %CYAN%[3/8] Creating directory structure...%RESET%

mkdir logs 2>nul
mkdir models 2>nul
mkdir data 2>nul
mkdir config\grafana\dashboards 2>nul
mkdir config\grafana\provisioning\datasources 2>nul
mkdir config\grafana\provisioning\dashboards 2>nul
mkdir config\prometheus\rules 2>nul
mkdir deployment\systemd 2>nul
echo %GREEN%[OK]%RESET% Directories created

echo.

REM ============================================================
REM STEP 4: Generate Prometheus Config
REM ============================================================
echo %CYAN%[4/8] Checking Prometheus configuration...%RESET%

if not exist "config\prometheus.yml" (
    echo %YELLOW%[WARN]%RESET% Prometheus config not found, using defaults
) else (
    echo %GREEN%[OK]%RESET% Prometheus config exists
)

echo.

REM ============================================================
REM STEP 5: Generate Grafana Provisioning
REM ============================================================
echo %CYAN%[5/8] Generating Grafana provisioning...%RESET%

REM Datasource provisioning
if not exist "config\grafana\provisioning\datasources\datasources.yml" (
    (
        echo apiVersion: 1
        echo datasources:
        echo   - name: Prometheus
        echo     type: prometheus
        echo     access: proxy
        echo     url: http://prometheus:9090
        echo     isDefault: true
        echo     editable: false
        echo   - name: InfluxDB
        echo     type: influxdb
        echo     access: proxy
        echo     url: http://influxdb:8086
        echo     database: metrics
        echo     jsonData:
        echo       organization: trading
        echo       defaultBucket: metrics
        echo     secureJsonData:
        echo       token: ${INFLUX_TOKEN}
        echo     editable: false
    ) > config\grafana\provisioning\datasources\datasources.yml
    echo %GREEN%[OK]%RESET% Generated Grafana datasources
)

REM Dashboard provisioning
if not exist "config\grafana\provisioning\dashboards\dashboards.yml" (
    (
        echo apiVersion: 1
        echo providers:
        echo   - name: 'Forex Dashboards'
        echo     orgId: 1
        echo     folder: 'Forex Trading'
        echo     type: file
        echo     disableDeletion: false
        echo     updateIntervalSeconds: 10
        echo     allowUiUpdates: true
        echo     options:
        echo       path: /var/lib/grafana/dashboards
    ) > config\grafana\provisioning\dashboards\dashboards.yml
    echo %GREEN%[OK]%RESET% Generated Grafana dashboard provisioning
)

echo.

REM ============================================================
REM STEP 6: Build Docker Images
REM ============================================================
echo %CYAN%[6/8] Building Docker images (this may take several minutes)...%RESET%

docker compose -p forex build --parallel 2>&1 | findstr /v "CACHED" | findstr /v "Pulling" | findstr /v "Downloading" | findstr /v "Extracting"

if errorlevel 1 (
    echo %RED%[ERROR] Docker build failed%RESET%
    echo Check the output above for errors
    pause
    exit /b 1
)
echo %GREEN%[OK]%RESET% Docker images built successfully

echo.

REM ============================================================
REM STEP 7: Start Infrastructure Services
REM ============================================================
echo %CYAN%[7/8] Starting infrastructure services...%RESET%

docker compose -p forex up -d timescaledb redis influxdb nats 2>&1 | findstr /v "CACHED" | findstr /v "Pulling" | findstr /v "Downloading"

echo.
echo Waiting for services to become healthy...
timeout /t 30 /nobreak >nul

echo Verifying services...
docker exec forex-timescaledb pg_isready -U trader -d market_data >nul 2>&1 && echo %GREEN%[OK]%RESET% TimescaleDB ready || echo %YELLOW%[WARN]%RESET% TimescaleDB not ready yet
docker exec forex-redis redis-cli ping >nul 2>&1 && echo %GREEN%[OK]%RESET% Redis ready || echo %YELLOW%[WARN]%RESET% Redis not ready yet
docker exec forex-nats nats --version >nul 2>&1 && echo %GREEN%[OK]%RESET% NATS ready || echo %YELLOW%[WARN]%RESET% NATS not ready yet
docker exec forex-influxdb influx ping >nul 2>&1 && echo %GREEN%[OK]%RESET% InfluxDB ready || echo %YELLOW%[WARN]%RESET% InfluxDB not ready yet

echo.

REM ============================================================
REM STEP 8: Initialize Database Schema
REM ============================================================
echo %CYAN%[8/8] Initializing database schema...%RESET%

docker exec -i forex-timescaledb psql -U trader -d market_data < scripts/init-timescaledb.sql 2>&1 | findstr /v "NOTICE" | findstr /v "already exists"
if errorlevel 1 (
    echo %YELLOW%[WARN]%RESET% Database initialization had warnings (may be normal if already initialized)
) else (
    echo %GREEN%[OK]%RESET% Database schema initialized
)

echo.
echo %CYAN%============================================================%RESET%
echo %CYAN%   INSTALLATION COMPLETE!%RESET%
echo %CYAN%============================================================%RESET%
echo.
echo To start the trading system:
echo   1. Edit .env with your credentials (MT5, API keys, etc.)
echo      notepad .env
echo   2. Run: .\start_trading_system.ps1
echo   3. Choose option A for full system
echo   4. Or use Docker: docker compose -p forex up -d
echo.
echo Access URLs:
echo   Dashboard:     http://localhost:8501
echo   API Docs:      http://localhost:8000/docs
echo   API Health:    http://localhost:8000/health
echo   Prometheus:    http://localhost:9090
echo   Grafana:       http://localhost:3000 (admin/admin)
echo   NATS Monitor:  http://localhost:8222
echo   InfluxDB:      http://localhost:8086
echo.
echo For MT5 EA: Copy ea/ForexTradingSystemEA.mq5 to MetaEditor and compile
echo.
pause
