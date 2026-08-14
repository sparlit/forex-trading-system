@echo off
REM ============================================================
REM Forex Trading System - Complete Startup Script
REM ============================================================
REM This script starts all components of the trading system:
REM 1. Docker infrastructure (TimescaleDB, Redis, InfluxDB, NATS)
REM 2. Data ingestion worker (MT5 + CCXT -> TimescaleDB/Redis)
REM 3. API server (FastAPI on port 8000)
REM 4. Streamlit Dashboard (port 8501)
REM 5. Bloomberg Terminal (TUI)
REM ============================================================

set PROJECT_DIR=C:\Users\sp\forex-trading-system
set COMPOSE_PROJECT=forex

echo.
echo ============================================================
echo  FOREX TRADING SYSTEM - STARTUP
echo ============================================================
echo Project: %PROJECT_DIR%
echo Docker Project: %COMPOSE_PROJECT%
echo.

REM Check if Docker Desktop is running
echo [1/6] Checking Docker Desktop...
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Docker Desktop is not running!
    echo Please start Docker Desktop and wait for it to be ready.
    pause
    exit /b 1
)
echo Docker OK
echo.

REM Check if MT5 terminal is running (informational)
echo [2/6] Checking MetaTrader 5...
tasklist /FI "IMAGENAME eq terminal64.exe" 2>nul | find "terminal64.exe" >nul
if %errorlevel% equ 0 (
    echo MT5 Terminal: RUNNING
) else (
    echo WARNING: MT5 Terminal not detected. Make sure it's running and logged in.
)
echo.

REM Start Docker infrastructure
echo [3/6] Starting Docker infrastructure (TimescaleDB, Redis, InfluxDB, NATS)...
cd /d %PROJECT_DIR%
docker compose -p %COMPOSE_PROJECT% up -d timescaledb redis influxdb nats --no-deps
if %errorlevel% neq 0 (
    echo ERROR: Failed to start Docker containers
    pause
    exit /b 1
)
echo Waiting for services to be healthy...
timeout 10 >nul
echo.

REM Verify infrastructure
echo [4/6] Verifying infrastructure connections...
docker exec forex-redis redis-cli ping >nul 2>&1
if %errorlevel% eq 0 (echo Redis: OK) else (echo Redis: FAILED)

docker exec forex-timescaledb pg_isready -U trader -d market_data >nul 2>&1
if %errorlevel% eq 0 (echo TimescaleDB: OK) else (echo TimescaleDB: FAILED)

docker exec forex-nats nats --version >nul 2>&1
if %errorlevel% eq 0 (echo NATS: OK) else (echo NATS: FAILED - CLI not in container, but service runs)
echo.

REM Menu for what to start
echo ============================================================
echo  SELECT COMPONENTS TO START
echo ============================================================
echo [A] All components (Data Worker + API + Dashboard + Terminal)
echo [B] Data Worker only
echo [C] Data Worker + Dashboard
echo [D] Data Worker + API + Dashboard
echo [Q] Quit (infrastructure stays running)
echo.
set /p CHOICE=Enter choice [A/B/C/D/Q]: 

if /i "%CHOICE%"=="A" goto START_ALL
if /i "%CHOICE%"=="B" goto START_WORKER_ONLY
if /i "%CHOICE%"=="C" goto START_WORKER_DASHBOARD
if /i "%CHOICE%"=="D" goto START_WORKER_API_DASHBOARD
if /i "%CHOICE%"=="Q" goto QUIT
echo Invalid choice. Starting all components...
goto START_ALL

:START_ALL
echo.
echo ============================================================
echo  STARTING ALL COMPONENTS IN SEPARATE WINDOWS
echo ============================================================
echo.

REM Start Data Ingestion Worker
echo Starting Data Ingestion Worker...
start "Forex Data Worker" cmd /k "cd /d %PROJECT_DIR% && poetry run python -m src.data.runner"
timeout /t 3 /nobreak >nul

REM Start API Server
echo Starting API Server (port 8000)...
start "Forex API" cmd /k "cd /d %PROJECT_DIR% && poetry run uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul

REM Start Streamlit Dashboard
echo Starting Streamlit Dashboard (port 8501)...
start "Forex Dashboard" cmd /k "cd /d %PROJECT_DIR% && poetry run streamlit run src/portfolio/dashboard/app.py"
timeout /t 3 /nobreak >nul

REM Start Bloomberg Terminal
echo Starting Bloomberg Terminal...
start "Bloomberg Terminal" cmd /k "cd /d %PROJECT_DIR% && poetry run python src/ui/bloomberg_terminal.py"
timeout /t 2 /nobreak >nul

goto SHOW_URLS

:START_WORKER_ONLY
echo.
echo Starting Data Ingestion Worker only...
cd /d %PROJECT_DIR%
poetry run python -m src.data.runner
goto END

:START_WORKER_DASHBOARD
echo.
echo Starting Data Worker + Dashboard in separate windows...
start "Forex Data Worker" cmd /k "cd /d %PROJECT_DIR% && poetry run python -m src.data.runner"
timeout /t 3 /nobreak >nul
start "Forex Dashboard" cmd /k "cd /d %PROJECT_DIR% && poetry run streamlit run src/portfolio/dashboard/app.py"
goto SHOW_URLS

:START_WORKER_API_DASHBOARD
echo.
echo Starting Data Worker + API + Dashboard in separate windows...
start "Forex Data Worker" cmd /k "cd /d %PROJECT_DIR% && poetry run python -m src.data.runner"
timeout /t 3 /nobreak >nul
start "Forex API" cmd /k "cd /d %PROJECT_DIR% && poetry run uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
start "Forex Dashboard" cmd /k "cd /d %PROJECT_DIR% && poetry run streamlit run src/portfolio/dashboard/app.py"
goto SHOW_URLS

:QUIT
echo.
echo Infrastructure left running. To stop: docker compose -p %COMPOSE_PROJECT% down
pause
exit /b 0

:SHOW_URLS
echo.
echo ============================================================
echo  SYSTEM RUNNING - ACCESS URLS
echo ============================================================
echo.
echo Dashboard:     http://localhost:8501
echo API Docs:      http://localhost:8000/docs
echo API Health:    http://localhost:8000/health
echo Bloomberg:     Running in separate terminal window
echo.
echo ============================================================
echo  VERIFICATION COMMANDS (run in new terminal)
echo ============================================================
echo Check bars in DB:
echo   docker exec forex-timescaledb psql -U trader -d market_data -c ^
echo   "SELECT s.symbol, COUNT(*) FROM market_data.bars b ^
echo   JOIN market_data.symbols s ON b.symbol_id=s.symbol_id ^
echo   WHERE b.is_complete=TRUE GROUP BY s.symbol"
echo.
echo Check Redis:
echo   docker exec forex-redis redis-cli --scan --pattern "tick:*"
echo   docker exec forex-redis redis-cli --scan --pattern "bar:*"
echo.
echo Stop all: docker compose -p %COMPOSE_PROJECT% down
echo ============================================================
echo.
echo Press any key to close this window (other windows stay open)...
pause >nul
exit /b 0

:END
echo.
echo Data worker stopped.
pause