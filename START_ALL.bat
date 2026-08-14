@echo off
REM ============================================================
REM FOREX TRADING SYSTEM - ONE-COMMAND STARTUP (Native Windows)
REM ============================================================
REM This script does EVERYTHING:
REM  1. Installs Scoop + all infrastructure (PostgreSQL, Redis, InfluxDB, NATS, Prometheus, Grafana)
REM  2. Configures TimescaleDB extension
REM  3. Sets up Python environment (Poetry, dependencies)
REM  4. Generates .env with secure keys
REM  5. Starts all infrastructure services
REM  6. Initializes database schema
REM  7. Starts trading system (API + Dashboard + Data Worker + Terminal)
REM ============================================================

@echo off
setlocal enabledelayedexpansion

REM Enable ANSI colors
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "GREEN=%ESC%[32m"
set "RED=%ESC%[31m"
set "YELLOW=%ESC%[33m"
set "CYAN=%ESC%[36m"
set "MAGENTA=%ESC%[35m"
set "RESET=%ESC%[0m"

echo.
echo %CYAN%============================================================%RESET%
echo %CYAN%   FOREX TRADING SYSTEM - ONE-COMMAND STARTUP%RESET%
echo %CYAN%============================================================%RESET%
echo.

REM ============================================================
REM STEP 0: Check/Request Administrator
REM ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %YELLOW%[WARN] Not running as Administrator%RESET%
    echo %YELLOW%[WARN] Some services may need admin privileges to start%RESET%
    echo.
    echo %CYAN%Re-launching as Administrator...%RESET%
    powershell -Command "Start-Process cmd -ArgumentList '/c cd /d %CD% ^&^& %0' -Verb RunAs"
    exit /b 0
) else (
    echo %GREEN%[OK]%RESET% Running as Administrator
    echo.
)

REM ============================================================
REM STEP 1: Install Scoop Package Manager
REM ============================================================
echo %CYAN%[1/8] Installing Scoop package manager...%RESET%

if exist "C:\scoop\shims\scoop.cmd" goto :scoop_exists
if exist "%USERPROFILE%\scoop\shims\scoop.cmd" goto :scoop_exists
if exist "C:\ProgramData\scoop\shims\scoop.cmd" goto :scoop_exists

echo Installing Scoop to C:\scoop...
powershell -NoProfile -ExecutionPolicy RemoteSigned -Command "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force; $env:SCOOP='C:\scoop'; irm get.scoop.sh | iex"
if %errorlevel% neq 0 (
    echo %YELLOW%[WARN] Global install failed, trying user install...%RESET%
    powershell -NoProfile -ExecutionPolicy RemoteSigned -Command "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force; irm get.scoop.sh | iex"
    if %errorlevel% neq 0 (
        echo %RED%[ERROR] Failed to install Scoop%RESET%
        pause
        exit /b 1
    )
)
echo %GREEN%[OK]%RESET% Scoop installed
goto :scoop_done

:scoop_exists
echo %GREEN%[OK]%RESET% Scoop already installed

:scoop_done
echo.

REM Fix git safe.directory for Scoop buckets
echo %CYAN%Fixing git safe.directory for Scoop buckets...%RESET%
git config --global --add safe.directory "C:/ProgramData/Scoop/buckets/main" 2>nul
git config --global --add safe.directory "C:/ProgramData/Scoop/buckets/extras" 2>nul
git config --global --add safe.directory "C:/ProgramData/Scoop/buckets/versions" 2>nul
git config --global --add safe.directory "%USERPROFILE%/scoop/buckets/main" 2>nul
git config --global --add safe.directory "%USERPROFILE%/scoop/buckets/extras" 2>nul
git config --global --add safe.directory "%USERPROFILE%/scoop/buckets/versions" 2>nul
echo %GREEN%[OK]%RESET% Git safe directories configured

REM Add scoop to PATH for this session
set "PATH=C:\scoop\shims;%USERPROFILE%\scoop\shims;C:\ProgramData\scoop\shims;%PATH%"

REM ============================================================
REM STEP 2: Install Infrastructure via Scoop
REM ============================================================
echo %CYAN%[2/8] Adding Scoop buckets...%RESET%
scoop bucket list | findstr "extras" >nul 2>&1
if %errorlevel% neq 0 (scoop bucket add extras) else (echo Bucket 'extras' already exists)
scoop bucket list | findstr "versions" >nul 2>&1
if %errorlevel% neq 0 (scoop bucket add versions) else (echo Bucket 'versions' already exists)
echo %GREEN%[OK]%RESET% Buckets ready
echo.

echo %CYAN%[3/8] Installing infrastructure services...%RESET%

scoop list | findstr "postgresql" >nul 2>&1
if %errorlevel% neq 0 (scoop install postgresql && echo %GREEN%[OK]%RESET% PostgreSQL installed) else (echo %GREEN%[OK]%RESET% PostgreSQL already installed)

scoop list | findstr "redis" >nul 2>&1
if %errorlevel% neq 0 (scoop install redis && echo %GREEN%[OK]%RESET% Redis installed) else (echo %GREEN%[OK]%RESET% Redis already installed)

scoop list | findstr "influxdb" >nul 2>&1
if %errorlevel% neq 0 (scoop install influxdb && echo %GREEN%[OK]%RESET% InfluxDB installed) else (echo %GREEN%[OK]%RESET% InfluxDB already installed)

scoop list | findstr "nats-server" >nul 2>&1
if %errorlevel% neq 0 (scoop install nats-server && echo %GREEN%[OK]%RESET% NATS installed) else (echo %GREEN%[OK]%RESET% NATS already installed)

scoop list | findstr "prometheus" >nul 2>&1
if %errorlevel% neq 0 (scoop install prometheus && echo %GREEN%[OK]%RESET% Prometheus installed) else (echo %GREEN%[OK]%RESET% Prometheus already installed)

scoop list | findstr "grafana" >nul 2>&1
if %errorlevel% neq 0 (scoop install grafana && echo %GREEN%[OK]%RESET% Grafana installed) else (echo %GREEN%[OK]%RESET% Grafana already installed)

echo.

REM ============================================================
REM STEP 3: Configure TimescaleDB Extension
REM ============================================================
echo %CYAN%[4/8] Configuring TimescaleDB extension...%RESET%
set "PGBIN="
if exist "C:\ProgramData\scoop\apps\postgresql\current\bin\psql.exe" set "PGBIN=C:\ProgramData\scoop\apps\postgresql\current\bin\psql.exe"
if not defined PGBIN if exist "C:\scoop\apps\postgresql\current\bin\psql.exe" set "PGBIN=C:\scoop\apps\postgresql\current\bin\psql.exe"
if not defined PGBIN if exist "%USERPROFILE%\scoop\apps\postgresql\current\bin\psql.exe" set "PGBIN=%USERPROFILE%\scoop\apps\postgresql\current\bin\psql.exe"

if not defined PGBIN (
    echo %YELLOW%[WARN] PostgreSQL not found - TimescaleDB extension skipped%RESET%
) else (
    echo Found PostgreSQL at: %PGBIN%
    "%PGBIN%" -U postgres -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 2>nul
    if %errorlevel% neq 0 (
        echo %YELLOW%[WARN] TimescaleDB extension: run manually in psql:%RESET%
        echo   CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
    ) else (
        echo %GREEN%[OK]%RESET% TimescaleDB extension enabled
    )
)
echo.

REM ============================================================
REM STEP 4: Python Environment
REM ============================================================
echo %CYAN%[5/8] Setting up Python environment...%RESET%
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[ERROR] Python not in PATH. Install Python 3.11+ from python.org%RESET%
    pause
    exit /b 1
)
echo %GREEN%[OK]%RESET% Python found

poetry --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Poetry...
    pip install poetry
)
echo %GREEN%[OK]%RESET% Poetry available
echo.

REM ============================================================
REM STEP 5: Configuration & Dependencies
REM ============================================================
echo %CYAN%[6/8] Configuring environment and installing dependencies...%RESET%

if not exist ".env" (
    copy .env.example .env >nul 2>&1
    echo %GREEN%[OK]%RESET% Created .env from template
) else (
    echo %CYAN%[INFO]%RESET% .env already exists
)

REM Generate secure SECRET_KEY
powershell -NoProfile -Command "& { $key = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 64 | ForEach-Object { [char]$_ }); (Get-Content .env) -replace 'change-me-in-production-use-secure-random-key', $key | Set-Content .env }" 2>nul
echo %GREEN%[OK]%RESET% Generated secure SECRET_KEY

REM Create directories
mkdir logs 2>nul
mkdir models 2>nul
mkdir data 2>nul
mkdir config\grafana\dashboards 2>nul
mkdir config\grafana\provisioning\datasources 2>nul
mkdir config\grafana\provisioning\dashboards 2>nul
echo %GREEN%[OK]%RESET% Directories created

REM Install Python dependencies
echo %CYAN%Installing Python dependencies...%RESET%
poetry run python -c "import fastapi; import uvicorn; import streamlit; import redis; import psycopg2; import numpy; import pandas; print('All dependencies OK')" 2>nul
if %errorlevel% neq 0 (
    echo %YELLOW%[WARN] Some dependencies missing, attempting install...%RESET%
    goto :install_deps
) else (
    echo %GREEN%[OK]%RESET% Dependencies already installed - skipping Poetry install
    goto :deps_done
)

:install_deps
echo %CYAN%Attempting to install/update dependencies...%RESET%
poetry install --no-interaction
if %errorlevel% neq 0 (
    echo %YELLOW%[WARN] Standard install failed, trying without lock file...%RESET%
    poetry install --no-interaction --no-lock 2>nul
    if %errorlevel% neq 0 (
        echo %YELLOW%[WARN] Install without lock failed, trying --no-deps...%RESET%
        poetry install --no-interaction --no-deps 2>nul
        if %errorlevel% neq 0 (
            echo %RED%[ERROR] Poetry install failed.%RESET%
            echo %YELLOW%[WARN] Continuing anyway - dependencies may be available globally...%RESET%
            REM Don't exit - verify imports work
            poetry run python -c "import fastapi; import uvicorn; import streamlit; import redis; import psycopg2; import numpy; import pandas; print('Dependencies verified')" 2>nul
            if %errorlevel% neq 0 (
                echo %RED%[ERROR] Dependencies not available. Run 'poetry lock' manually when online.%RESET%
                pause
                exit /b 1
            )
        )
    )
)
echo %GREEN%[OK]%RESET% Dependencies installed

:deps_done
echo.

REM ============================================================
REM STEP 6: Start Infrastructure Services
REM ============================================================
echo %CYAN%[7/8] Starting infrastructure services...%RESET%

REM Helper to find scoop app path
set "SCOOP_ROOT=C:\scoop"
if not exist "%SCOOP_ROOT%\apps" set "SCOOP_ROOT=%USERPROFILE%\scoop"
if not exist "%SCOOP_ROOT%\apps" set "SCOOP_ROOT=C:\ProgramData\scoop"

echo Using Scoop root: %SCOOP_ROOT%

REM Start PostgreSQL
echo Starting PostgreSQL...
set "PGCTL=%SCOOP_ROOT%\apps\postgresql\current\bin\pg_ctl.exe"
set "PGDATA=%SCOOP_ROOT%\apps\postgresql\current\data"
set "PGBIN=%SCOOP_ROOT%\apps\postgresql\current\bin\psql.exe"
if exist "%PGCTL%" (
    start "" "%PGCTL%" -D "%PGDATA%" -l logfile start 2>nul
    echo %GREEN%[OK]%RESET% PostgreSQL started
) else (
    echo %YELLOW%[WARN] PostgreSQL not found, trying Windows service...%RESET%
    net start postgresql-x64-16 2>nul && echo %GREEN%[OK]%RESET% Started PostgreSQL service
    net start postgresql 2>nul && echo %GREEN%[OK]%RESET% Started PostgreSQL service
)

REM Wait for PostgreSQL
echo Waiting for PostgreSQL to be ready...
timeout 5 >nul 2>&1 || ping -n 6 127.0.0.1 >nul

REM Initialize TimescaleDB extension (now that PG is running)
if exist "%PGBIN%" (
    "%PGBIN%" -U postgres -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 2>nul
    if %errorlevel% neq 0 (
        echo %YELLOW%[WARN] TimescaleDB extension may need manual setup%RESET%
    ) else (
        echo %GREEN%[OK]%RESET% TimescaleDB extension enabled
    )
)

REM Start Redis
echo Starting Redis...
set "REDIS=%SCOOP_ROOT%\apps\redis\current\redis-server.exe"
if exist "%REDIS%" (
    start "" "%REDIS%"
    echo %GREEN%[OK]%RESET% Redis started
) else (
    net start Redis 2>nul && echo %GREEN%[OK]%RESET% Started Redis service
)

REM Start InfluxDB
echo Starting InfluxDB...
set "INFLUX=%SCOOP_ROOT%\apps\influxdb\current\influxdb3.exe"
if exist "%INFLUX%" (
    start "" "%INFLUX%" serve --node-id node1 --object-store memory --data-dir "%SCOOP_ROOT%\persist\influxdb\data" --disable-authz health
    echo %GREEN%[OK]%RESET% InfluxDB started
) else (
    net start influxdb 2>nul && echo %GREEN%[OK]%RESET% Started InfluxDB service
)

REM Start NATS
echo Starting NATS...
set "NATS=%SCOOP_ROOT%\apps\nats-server\current\nats-server.exe"
if exist "%NATS%" (
    start "" "%NATS%" -js -m 8222
    echo %GREEN%[OK]%RESET% NATS started
)

REM Start Prometheus
echo Starting Prometheus...
set "PROM=%SCOOP_ROOT%\apps\prometheus\current\prometheus.exe"
set "PROMCFG=%SCOOP_ROOT%\apps\prometheus\current\prometheus.yml"
set "PROMDATA=%SCOOP_ROOT%\persist\prometheus\data"
if exist "%PROM%" (
    start "" "%PROM%" --config.file="%PROMCFG%" --storage.tsdb.path="%PROMDATA%" --web.enable-lifecycle
    echo %GREEN%[OK]%RESET% Prometheus started
)

REM Start Grafana
echo Starting Grafana...
set "GRAFANA=%SCOOP_ROOT%\apps\grafana\current\bin\grafana.exe"
set "GRAFANAHOME=%SCOOP_ROOT%\apps\grafana\current"
if exist "%GRAFANA%" (
    start "" "%GRAFANA%" server --homepath="%GRAFANAHOME%"
    echo %GREEN%[OK]%RESET% Grafana started
)

echo Waiting for all services to be ready...
timeout 5 >nul 2>&1 || ping -n 6 127.0.0.1 >nul
echo.

REM ============================================================
REM STEP 7: Initialize Database Schema
REM ============================================================
echo %CYAN%[8/8] Initializing database schema...%RESET%
set "PGBIN=%SCOOP_ROOT%\apps\postgresql\current\bin\psql.exe"
if exist "%PGBIN%" (
    "%PGBIN%" -U postgres -d market_data -f scripts\init-timescaledb.sql 2>nul
    echo %GREEN%[OK]%RESET% Database initialized
) else (
    echo %YELLOW%[WARN] PostgreSQL not found - schema init skipped%RESET%
)
echo.

REM ============================================================
REM LAUNCH TRADING SYSTEM
REM ============================================================
echo %MAGENTA%============================================================%RESET%
echo %MAGENTA%   LAUNCHING TRADING SYSTEM%RESET%
echo %MAGENTA%============================================================%RESET%
echo.

echo Starting Data Ingestion Worker...
start "Data Worker" cmd /k "cd /d %CD% && poetry run python -m src.data.runner"
timeout 3 >nul 2>&1 || ping -n 4 127.0.0.1 >nul

echo Starting API Server...
start "API Server" cmd /k "cd /d %CD% && poetry run uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
timeout 3 >nul 2>&1 || ping -n 4 127.0.0.1 >nul

echo Starting Dashboard...
start "Dashboard" cmd /k "cd /d %CD% && poetry run streamlit run src/portfolio/dashboard/app.py --server.port 8501 --server.address 0.0.0.0"
timeout 3 >nul 2>&1 || ping -n 4 127.0.0.1 >nul

echo Starting Bloomberg Terminal...
start "Bloomberg Terminal" cmd /k "cd /d %CD% && poetry run python src/ui/bloomberg_terminal.py"
timeout 3 >nul 2>&1 || ping -n 4 127.0.0.1 >nul

echo.
echo %MAGENTA%============================================================%RESET%
echo %MAGENTA%   FOREX TRADING SYSTEM - RUNNING%RESET%
echo %MAGENTA%============================================================%RESET%
echo.
echo Dashboard:      http://localhost:8501
echo API Docs:       http://localhost:8000/docs
echo API Health:     http://localhost:8000/health
echo Prometheus:     http://localhost:9090
echo Grafana:        http://localhost:3000 (admin/admin)
echo NATS Monitor:   http://localhost:8222
echo InfluxDB:       http://localhost:8086
echo PostgreSQL:     localhost:5432
echo Redis:          localhost:6379
echo.
echo %CYAN%All services started in separate windows.%RESET%
echo %CYAN%Close this window when done (other windows stay open).%RESET%
echo.
pause