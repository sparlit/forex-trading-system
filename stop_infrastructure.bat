@echo off
REM ============================================================
REM Stop Infrastructure Services (Native Windows)
REM ============================================================

@echo off
setlocal

echo.
echo Stopping infrastructure services...

taskkill /F /IM postgres.exe 2>nul && echo Stopped PostgreSQL
taskkill /F /IM redis-server.exe 2>nul && echo Stopped Redis
taskkill /F /IM influxdb3.exe 2>nul && echo Stopped InfluxDB
taskkill /F /IM nats-server.exe 2>nul && echo Stopped NATS
taskkill /F /IM prometheus.exe 2>nul && echo Stopped Prometheus
taskkill /F /IM grafana.exe 2>nul && echo Stopped Grafana

echo.
echo All infrastructure services stopped.
pause
