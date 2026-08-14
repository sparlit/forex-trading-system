@echo off
REM ============================================================
REM Start Infrastructure Services (Native Windows)
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
echo %CYAN%   STARTING INFRASTRUCTURE SERVICES%RESET%
echo %CYAN%============================================================%RESET%
echo.

REM Helper to find scoop app path - check all possible locations
set "SCOOP_ROOT=C:\scoop"
if not exist "%SCOOP_ROOT%\apps" set "SCOOP_ROOT=%USERPROFILE%\scoop"
if not exist "%SCOOP_ROOT%\apps" set "SCOOP_ROOT=C:\ProgramData\scoop"

echo %CYAN%Using Scoop root: %SCOOP_ROOT%%RESET%
echo.

REM Start PostgreSQL FIRST (needed for TimescaleDB)
echo %CYAN%Starting PostgreSQL...%RESET%
set "PGCTL=%SCOOP_ROOT%\apps\postgresql\current\bin\pg_ctl.exe"
set "PGDATA=%SCOOP_ROOT%\apps\postgresql\current\data"
set "PGBIN=%SCOOP_ROOT%\apps\postgresql\current\bin\psql.exe"
if exist "%PGCTL%" (
    start "" "%PGCTL%" -D "%PGDATA%" -l logfile start 2>nul
    echo %GREEN%[OK]%RESET% PostgreSQL start initiated at %PGCTL%
) else (
    echo %YELLOW%[WARN] PostgreSQL not found at %PGCTL%%RESET%
    echo Trying default PostgreSQL Windows service...
    net start postgresql-x64-16 2>nul && echo %GREEN%[OK]%RESET% Started PostgreSQL Windows service
    net start postgresql 2>nul && echo %GREEN%[OK]%RESET% Started PostgreSQL Windows service
)

REM Wait for PostgreSQL to be ready
echo %CYAN%Waiting for PostgreSQL to be ready...%RESET%
timeout 5 >nul 2>&1 || ping -n 6 127.0.0.1 >nul

REM Initialize TimescaleDB extension NOW that PostgreSQL is running
echo %CYAN%Configuring TimescaleDB extension...%RESET%
set "PGBIN=%SCOOP_ROOT%\apps\postgresql\current\bin\psql.exe"
if exist "%PGBIN%" (
    "%PGBIN%" -U postgres -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 2>nul
    if errorlevel 1 (
        echo %YELLOW%[WARN] TimescaleDB extension may already exist or need manual setup%RESET%
    ) else (
        echo %GREEN%[OK]%RESET% TimescaleDB extension enabled
    )
) else (
    echo %YELLOW%[WARN] psql not found - TimescaleDB extension skipped%RESET%
)

REM Redis
echo %CYAN%Starting Redis...%RESET%
set "REDIS=%SCOOP_ROOT%\apps\redis\current\redis-server.exe"
if exist "%REDIS%" (
    start "" "%REDIS%"
    echo %GREEN%[OK]%RESET% Redis started at %REDIS%
) else (
    echo %YELLOW%[WARN] Redis not found at %REDIS%%RESET%
    echo Trying Redis Windows service...
    net start Redis 2>nul && echo %GREEN%[OK]%RESET% Started Redis Windows service
)

REM InfluxDB
echo %CYAN%Starting InfluxDB...%RESET%
set "INFLUX=%SCOOP_ROOT%\apps\influxdb\current\influxdb3.exe"
if exist "%INFLUX%" (
    start "" "%INFLUX%" serve --node-id node1 --object-store memory --data-dir "%SCOOP_ROOT%\persist\influxdb\data" --disable-authz health
    echo %GREEN%[OK]%RESET% InfluxDB started at %INFLUX%
) else (
    echo %YELLOW%[WARN] InfluxDB not found at %INFLUX%%RESET%
    echo Trying InfluxDB Windows service...
    net start influxdb 2>nul && echo %GREEN%[OK]%RESET% Started InfluxDB Windows service
)

REM NATS
echo %CYAN%Starting NATS...%RESET%
set "NATS=%SCOOP_ROOT%\apps\nats-server\current\nats-server.exe"
if exist "%NATS%" (
    start "" "%NATS%" -js -m 8222
    echo %GREEN%[OK]%RESET% NATS started at %NATS%
) else (
    echo %YELLOW%[WARN] NATS not found at %NATS%%RESET%
)

REM Prometheus
echo %CYAN%Starting Prometheus...%RESET%
set "PROM=%SCOOP_ROOT%\apps\prometheus\current\prometheus.exe"
set "PROMCFG=%SCOOP_ROOT%\apps\prometheus\current\prometheus.yml"
set "PROMDATA=%SCOOP_ROOT%\persist\prometheus\data"
if exist "%PROM%" (
    start "" "%PROM%" --config.file="%PROMCFG%" --storage.tsdb.path="%PROMDATA%" --web.enable-lifecycle
    echo %GREEN%[OK]%RESET% Prometheus started at %PROM%
) else (
    echo %YELLOW%[WARN] Prometheus not found at %PROM%%RESET%
)

REM Grafana
echo %CYAN%Starting Grafana...%RESET%
set "GRAFANA=%SCOOP_ROOT%\apps\grafana\current\bin\grafana.exe"
set "GRAFANAHOME=%SCOOP_ROOT%\apps\grafana\current"
if exist "%GRAFANA%" (
    start "" "%GRAFANA%" server --homepath="%GRAFANAHOME%"
    echo %GREEN%[OK]%RESET% Grafana started at %GRAFANA%
) else (
    echo %YELLOW%[WARN] Grafana not found at %GRAFANA%%RESET%
)

echo.
echo Waiting for all services to be ready...
timeout 5 >nul 2>&1 || ping -n 6 127.0.0.1 >nul

echo.
echo %CYAN%============================================================%RESET%
echo %CYAN%   INFRASTRUCTURE STARTED%RESET%
echo %CYAN%============================================================%RESET%
echo.
echo Access URLs:
echo   PostgreSQL:    localhost:5432
echo   Redis:         localhost:6379
echo   InfluxDB:      http://localhost:8086
echo   NATS:          localhost:4222 (monitor: 8222)
echo   Prometheus:    http://localhost:9090
echo   Grafana:       http://localhost:3000 (admin/admin)
echo.
echo To stop: .\stop_infrastructure.bat
echo.
pause
