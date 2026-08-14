@echo off
REM ============================================================
REM Start Trading System (Native Windows - No Docker)
REM ============================================================

@echo off
setlocal enabledelayedexpansion

for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "GREEN=%ESC%[32m"
set "RED=%ESC%[31m"
set "YELLOW=%ESC%[33m"
set "CYAN=%ESC%[36m"
set "RESET=%ESC%[0m"

echo.
echo %CYAN%============================================================%RESET%
echo %CYAN%   FOREX TRADING SYSTEM - NATIVE START%RESET%
echo %CYAN%============================================================%RESET%
echo.

REM Check .env exists
if not exist ".env" (
    echo %RED%[ERROR] .env not found! Run INSTALL_NATIVE.bat first%RESET%
    pause
    exit /b 1
)

REM Check Python dependencies (skip poetry install if already available)
echo %CYAN%Checking Python dependencies...%RESET%
python -c "import fastapi; import uvicorn; import streamlit; import redis; import psycopg2; import numpy; import pandas; print('All dependencies OK')" 2>nul
if %errorlevel% neq 0 goto :install_deps

echo %GREEN%[OK]%RESET% Dependencies already installed
echo.
goto :deps_done

:install_deps
echo %CYAN%Installing Python dependencies...%RESET%
REM Try to install using existing lock file (offline mode if network unavailable)
poetry install --no-interaction
if %errorlevel% neq 0 goto :install_no_lock
goto :deps_done

:install_no_lock
echo %YELLOW%[WARN] poetry install failed (lock file may be out of sync), trying without lock...%RESET%
poetry install --no-interaction --no-lock 2>nul
if %errorlevel% neq 0 goto :install_no_deps
goto :deps_done

:install_no_deps
echo %YELLOW%[WARN] poetry install without lock failed, trying --no-deps...%RESET%
poetry install --no-interaction --no-deps 2>nul
if %errorlevel% neq 0 goto :deps_fail
goto :deps_done

:deps_fail
echo %RED%[ERROR] Failed to install dependencies. Run 'poetry lock' manually when online, then retry.%RESET%
pause
exit /b 1

:deps_done
echo.

REM Initialize database schema
echo %CYAN%Initializing database schema...%RESET%
set "SCOOP_ROOT=C:\scoop"
if not exist "%SCOOP_ROOT%\apps" set "SCOOP_ROOT=%USERPROFILE%\scoop"
if not exist "%SCOOP_ROOT%\apps" set "SCOOP_ROOT=C:\ProgramData\scoop"
set "PGBIN=%SCOOP_ROOT%\apps\postgresql\current\bin\psql.exe"
if exist "%PGBIN%" (
    "%PGBIN%" -U postgres -d market_data -f scripts\init-timescaledb.sql 2>nul
    echo %GREEN%[OK]%RESET% Database initialized
) else (
    echo %YELLOW%[WARN] PostgreSQL not found - schema init skipped%RESET%
)
echo.

echo %CYAN%============================================================%RESET%
echo %CYAN%   SELECT COMPONENTS TO START%RESET%
echo %CYAN%============================================================%RESET%
echo.
echo [1] All components (Data Worker + API + Dashboard + Terminal)
echo [2] Data Worker only
echo [3] Data Worker + Dashboard
echo [4] Data Worker + API + Dashboard
echo [5] API only
echo [6] Dashboard only
echo [Q] Quit
echo.

set /p choice=Enter choice [1/2/3/4/5/6/Q]:

if "%choice%"=="Q" goto :quit
if "%choice%"=="q" goto :quit

echo.
echo %CYAN%Starting selected components...%RESET%
echo.

if "%choice%"=="1" goto :all
if "%choice%"=="2" goto :worker
if "%choice%"=="3" goto :worker_dash
if "%choice%"=="4" goto :worker_api_dash
if "%choice%"=="5" goto :api_only
if "%choice%"=="6" goto :dash_only
goto :all

:all
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
goto :show_urls

:worker
echo Starting Data Ingestion Worker...
start "Data Worker" cmd /k "cd /d %CD% && poetry run python -m src.data.runner"
goto :show_urls

:worker_dash
echo Starting Data Worker + Dashboard...
start "Data Worker" cmd /k "cd /d %CD% && poetry run python -m src.data.runner"
timeout 3 >nul 2>&1 || ping -n 4 127.0.0.1 >nul
start "Dashboard" cmd /k "cd /d %CD% && poetry run streamlit run src/portfolio/dashboard/app.py --server.port 8501 --server.address 0.0.0.0"
goto :show_urls

:worker_api_dash
echo Starting Data Worker + API + Dashboard...
start "Data Worker" cmd /k "cd /d %CD% && poetry run python -m src.data.runner"
timeout 3 >nul 2>&1 || ping -n 4 127.0.0.1 >nul
start "API Server" cmd /k "cd /d %CD% && poetry run uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
timeout 3 >nul 2>&1 || ping -n 4 127.0.0.1 >nul
start "Dashboard" cmd /k "cd /d %CD% && poetry run streamlit run src/portfolio/dashboard/app.py --server.port 8501 --server.address 0.0.0.0"
goto :show_urls

:api_only
echo Starting API Server...
start "API Server" cmd /k "cd /d %CD% && poetry run uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
goto :show_urls

:dash_only
echo Starting Dashboard...
start "Dashboard" cmd /k "cd /d %CD% && poetry run streamlit run src/portfolio/dashboard/app.py --server.port 8501 --server.address 0.0.0.0"
goto :show_urls

:show_urls
echo.
echo %CYAN%============================================================%RESET%
echo %CYAN%   SYSTEM RUNNING%RESET%
echo %CYAN%============================================================%RESET%
echo.
echo Dashboard:     http://localhost:8501
echo API Docs:      http://localhost:8000/docs
echo API Health:    http://localhost:8000/health
echo Prometheus:    http://localhost:9090
echo Grafana:       http://localhost:3000 (admin/admin)
echo NATS Monitor:  http://localhost:8222
echo InfluxDB:      http://localhost:8086
echo.
echo Press any key to close this window (other windows stay open)....
pause >nul
:quit
exit /b 0