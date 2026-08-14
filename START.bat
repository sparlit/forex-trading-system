@echo off
REM ============================================================
REM Forex Trading System - Quick Start Script
REM ============================================================

@echo off
setlocal

echo.
echo ==============================================================
echo   FOREX TRADING SYSTEM - QUICK START
echo ==============================================================
echo.

REM Check Docker
docker version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop not running!
    echo Please start Docker Desktop first.
    pause
    exit /b 1
)

echo [OK] Docker is running
echo.

REM Start infrastructure
echo Starting infrastructure...
docker compose -p forex up -d timescaledb redis influxdb nats

echo Waiting for services...
timeout /t 15 /nobreak >nul

REM Start full stack
echo Starting full trading system...
docker compose -p forex up -d

echo.
echo System starting! Access URLs:
echo   Dashboard:     http://localhost:8501
echo   API Docs:      http://localhost:8000/docs
echo   API Health:    http://localhost:8000/health
echo   Grafana:       http://localhost:3000 (admin/admin)
echo.
echo To stop: docker compose -p forex down
echo.
pause
