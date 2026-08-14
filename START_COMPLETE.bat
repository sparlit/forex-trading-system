@echo off
REM ============================================================================
REM Elite Autonomous Quantum Trading System - Complete Startup Script
REM Starts both the autonomous trading system and the Streamlit dashboard
REM ============================================================================

set PROJECT_ROOT=D:\forex-trading-system
cd /d %PROJECT_ROOT%

echo.
echo ============================================================================
echo    ELITE AUTONOMOUS QUANTUM TRADING SYSTEM - STARTUP
echo    100%% Autonomous ^| Zero User Input ^| Self-Evolving Brain
echo ============================================================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH
    pause
    exit /b 1
)

echo [INFO] Python found:
python --version

REM Create required directories
if not exist logs mkdir logs
if not exist data\brain_state mkdir data\brain_state

echo.
echo [1/3] Starting infrastructure services...
REM Start Redis, PostgreSQL, InfluxDB, NATS if not running
start_infrastructure.bat

echo.
echo [2/3] Starting Autonomous Trading System (backend)...
start "Autonomous Trading System" cmd /k "cd /d %PROJECT_ROOT% && python -m src.autonomous_main"

REM Give the backend time to start
timeout /t 5 >nul

echo.
echo [3/3] Starting Streamlit Dashboard (frontend)...
start "Trading Dashboard" cmd /k "cd /d %PROJECT_ROOT% && streamlit run src/dashboard/app.py --server.port 8501 --server.address 0.0.0.0"

echo.
echo ============================================================================
echo    SYSTEM STARTED SUCCESSFULLY
echo ============================================================================
echo.
echo    Autonomous Backend:  Running in background window
echo    Streamlit Dashboard: http://localhost:8501
echo    API Server:          http://localhost:8000
echo.
echo    Press Ctrl+C in the backend window to stop the system
echo ============================================================================
echo.

pause
