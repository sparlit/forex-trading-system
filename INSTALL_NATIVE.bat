@echo off
REM ============================================================
REM Forex Trading System - Native Windows Installation (No Docker)
REM ============================================================
REM This script installs all infrastructure natively on Windows using Scoop
REM ============================================================

@echo off
setlocal enabledelayedexpansion

REM Enable ANSI colors
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "GREEN=%ESC%[32m"
set "RED=%ESC%[31m"
set "YELLOW=%ESC%[33m"
set "CYAN=%ESC%[36m"
set "RESET=%ESC%[0m"

echo.
echo %CYAN%============================================================%RESET%
echo %CYAN%   FOREX TRADING SYSTEM - NATIVE WINDOWS INSTALL%RESET%
echo %CYAN%============================================================%RESET%
echo.

REM Check Administrator
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo %YELLOW%[WARN] Not running as Administrator - some services may need admin later%RESET%
    echo.
) else (
    echo %GREEN%[OK]%RESET% Running as Administrator
    echo.
)

REM ============================================================
REM STEP 1: Install Scoop Package Manager
REM ============================================================
echo %CYAN%[1/10] Installing Scoop package manager...%RESET%

REM Check both possible Scoop locations
if exist "C:\\scoop\\shims\\scoop.cmd" goto :scoop_exists
if exist "%USERPROFILE%\\scoop\\shims\\scoop.cmd" goto :scoop_exists
if exist "C:\\ProgramData\\scoop\\shims\\scoop.cmd" goto :scoop_exists

echo Installing Scoop...
REM Install to C:\\scoop (global) - works with admin by setting SCOOP env var
powershell -NoProfile -ExecutionPolicy RemoteSigned -Command "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force; $env:SCOOP='C:\\scoop'; irm get.scoop.sh | iex"
if errorlevel 1 (
    echo %YELLOW%[WARN] Global install failed, trying user install...%RESET%
    powershell -NoProfile -ExecutionPolicy RemoteSigned -Command "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force; irm get.scoop.sh | iex"
    if errorlevel 1 (
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

REM Fix git safe.directory for Scoop buckets (common issue)
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
echo %CYAN%[2/10] Adding Scoop buckets...%RESET%
scoop bucket list | findstr "extras" >nul 2>&1
if errorlevel 1 (
    scoop bucket add extras
) else (
    echo Bucket 'extras' already exists
)

scoop bucket list | findstr "versions" >nul 2>&1
if errorlevel 1 (
    scoop bucket add versions
) else (
    echo Bucket 'versions' already exists
)
echo %GREEN%[OK]%RESET% Buckets ready
echo.

echo %CYAN%[3/10] Installing PostgreSQL (TimescaleDB)...%RESET%
scoop list | findstr "postgresql" >nul 2>&1
if errorlevel 1 (
    scoop install postgresql
    if errorlevel 1 (
        echo %YELLOW%[WARN] PostgreSQL install had issues%RESET%
    ) else (
        echo %GREEN%[OK]%RESET% PostgreSQL installed
    )
) else (
    echo %GREEN%[OK]%RESET% PostgreSQL already installed
)
echo.

echo %CYAN%[4/10] Installing Redis...%RESET%
scoop list | findstr "redis" >nul 2>&1
if errorlevel 1 (
    scoop install redis
    if errorlevel 1 (
        echo %YELLOW%[WARN] Redis install had issues%RESET%
    ) else (
        echo %GREEN%[OK]%RESET% Redis installed
    )
) else (
    echo %GREEN%[OK]%RESET% Redis already installed
)
echo.

echo %CYAN%[5/10] Installing InfluxDB...%RESET%
scoop list | findstr "influxdb" >nul 2>&1
if errorlevel 1 (
    scoop install influxdb
    if errorlevel 1 (
        echo %YELLOW%[WARN] InfluxDB install had issues%RESET%
    ) else (
        echo %GREEN%[OK]%RESET% InfluxDB installed
    )
) else (
    echo %GREEN%[OK]%RESET% InfluxDB already installed
)
echo.

echo %CYAN%[6/10] Installing NATS Server...%RESET%
scoop list | findstr "nats-server" >nul 2>&1
if errorlevel 1 (
    scoop install nats-server
    if errorlevel 1 (
        echo %YELLOW%[WARN] NATS install had issues%RESET%
    ) else (
        echo %GREEN%[OK]%RESET% NATS installed
    )
) else (
    echo %GREEN%[OK]%RESET% NATS already installed
)
echo.

echo %CYAN%[7/10] Installing Prometheus...%RESET%
scoop list | findstr "prometheus" >nul 2>&1
if errorlevel 1 (
    scoop install prometheus
    if errorlevel 1 (
        echo %YELLOW%[WARN] Prometheus install had issues%RESET%
    ) else (
        echo %GREEN%[OK]%RESET% Prometheus installed
    )
) else (
    echo %GREEN%[OK]%RESET% Prometheus already installed
)
echo.

echo %CYAN%[8/10] Installing Grafana...%RESET%
scoop list | findstr "grafana" >nul 2>&1
if errorlevel 1 (
    scoop install grafana
    if errorlevel 1 (
        echo %YELLOW%[WARN] Grafana install had issues%RESET%
    ) else (
        echo %GREEN%[OK]%RESET% Grafana installed
    )
) else (
    echo %GREEN%[OK]%RESET% Grafana already installed
)
echo.

REM ============================================================
REM STEP 3: Initialize TimescaleDB Extension
REM ============================================================
echo %CYAN%[9/10] Configuring TimescaleDB extension...%RESET%
set "PGBIN="
REM Check multiple possible PostgreSQL locations
if exist "C:\ProgramData\scoop\apps\postgresql\current\bin\psql.exe" set "PGBIN=C:\ProgramData\scoop\apps\postgresql\current\bin\psql.exe"
if not defined PGBIN if exist "C:\scoop\apps\postgresql\current\bin\psql.exe" set "PGBIN=C:\scoop\apps\postgresql\current\bin\psql.exe"
if not defined PGBIN if exist "%USERPROFILE%\scoop\apps\postgresql\current\bin\psql.exe" set "PGBIN=%USERPROFILE%\scoop\apps\postgresql\current\bin\psql.exe"
if not defined PGBIN if exist "C:\ProgramData\scoop\apps\postgresql\current\bin\pg_ctl.exe" (
    echo %YELLOW%[WARN] Found pg_ctl but not psql, trying to find psql...%RESET%
    for %%f in ("C:\ProgramData\scoop\apps\postgresql\current\bin\*.exe") do if "%%~nf"=="psql" set "PGBIN=%%f"
)
if not defined PGBIN (
    echo %YELLOW%[WARN] PostgreSQL not found - TimescaleDB extension skipped%RESET%
) else (
    echo %CYAN%Found PostgreSQL at: %PGBIN%%RESET%
    "%PGBIN%" -U postgres -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 2>nul
    if errorlevel 1 (
        echo %YELLOW%[WARN] TimescaleDB extension: run manually: CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;%RESET%
    ) else (
        echo %GREEN%[OK]%RESET% TimescaleDB extension enabled
    )
)
echo.

REM ============================================================
REM STEP 4: Python Environment
REM ============================================================
echo %CYAN%[10/10] Setting up Python environment...%RESET%
python --version >nul 2>&1
if errorlevel 1 (
    echo %YELLOW%[WARN] Python not in PATH. Install Python 3.11+ from python.org%RESET%
) else (
    echo %GREEN%[OK]%RESET% Python found
    poetry --version >nul 2>&1
    if errorlevel 1 (
        echo Installing Poetry...
        pip install poetry
    )
    echo %GREEN%[OK]%RESET% Poetry available
)
echo.

REM ============================================================
REM FINAL: Generate .env and directories
REM ============================================================
echo %CYAN%============================================================%RESET%
echo %CYAN%   CREATING CONFIGURATION%RESET%
echo %CYAN%============================================================%RESET%

if not exist ".env" (
    copy .env.example .env >nul
    echo %GREEN%[OK]%RESET% Created .env from template
) else (
    echo %CYAN%[INFO]%RESET% .env already exists
)

powershell -NoProfile -Command "& { $key = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 64 | ForEach-Object { [char]$_ }); (Get-Content .env) -replace 'change-me-in-production-use-secure-random-key', \$key | Set-Content .env }" 2>nul
echo %GREEN%[OK]%RESET% Generated secure SECRET_KEY

mkdir logs 2>nul
mkdir models 2>nul
mkdir data 2>nul
mkdir config\grafana\dashboards 2>nul
mkdir config\grafana\provisioning\datasources 2>nul
mkdir config\grafana\provisioning\dashboards 2>nul
echo %GREEN%[OK]%RESET% Directories created

echo.
echo %CYAN%============================================================%RESET%
echo %CYAN%   NATIVE INSTALLATION COMPLETE!%RESET%
echo %CYAN%============================================================%RESET%
echo.
echo Next steps:
echo   1. Edit .env with your credentials: notepad .env
echo   2. Start infrastructure: .\start_infrastructure.bat
echo   3. Start trading system: .\start_native.bat
echo.
pause
