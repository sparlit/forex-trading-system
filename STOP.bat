@echo off
REM ============================================================
REM Elite Autonomous Quantum Trading System - GRACEFUL SHUTDOWN
REM Single command: STOP
REM ============================================================

@echo off
setlocal enabledelayedexpansion

REM Colors
set GREEN=\033[92m
set RED=\033[91m
set YELLOW=\033[93m
set CYAN=\033[96m
set RESET=\033[0m

echo.
echo %RED%============================================================%RESET%
echo %RED%  ELITE AUTONOMOUS QUANTUM TRADING SYSTEM - SHUTDOWN%RESET%
echo %RED%============================================================%RESET%
echo.

REM ------------------------------------------------------------
REM 1. STOP MT5 EA (Instructions)
REM ------------------------------------------------------------
echo %CYAN%[STEP]%RESET% MT5 EA Shutdown Instructions:
echo %YELLOW%  1. In MT5, remove EA from all charts%RESET%
echo %YELLOW%  2. Disable AutoTrading button in toolbar%RESET%
echo %YELLOW%  3. Close MetaEditor if open%RESET%
echo.

REM ------------------------------------------------------------
REM 2. STOP APPLICATION SERVICES
REM ------------------------------------------------------------
echo %CYAN%[STEP]%RESET% Stopping application services...

echo %CYAN%  Stopping Dashboard (streamlit)...%RESET%
taskkill /f /im streamlit.exe >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%  [OK]%RESET% Dashboard stopped
) else (
    echo %YELLOW%  [INFO]%RESET% Dashboard was not running
)

echo %CYAN%  Stopping API Server (uvicorn)...%RESET%
taskkill /f /im uvicorn.exe >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%  [OK]%RESET% API Server stopped
) else (
    echo %YELLOW%  [INFO]%RESET% API Server was not running
)

echo %CYAN%  Stopping Python workers...%RESET%
taskkill /f /fi "windowtitle eq *python*" /im python.exe >nul 2>&1
if !errorlevel! equ 0 (
    echo %GREEN%  [OK]%RESET% Python workers stopped
) else (
    echo %YELLOW%  [INFO]%RESET% No python workers found
)

REM ------------------------------------------------------------
REM 3. STOP INFRASTRUCTURE (Optional)
REM ------------------------------------------------------------
echo.
echo %CYAN%[STEP]%RESET% Infrastructure shutdown (optional):%RESET%
set /p CHOICE="Stop PostgreSQL and Redis? (y/N): "
if /i "!CHOICE!"=="y" (
    echo %CYAN%  Stopping Redis...%RESET%
    redis-cli shutdown >nul 2>&1
    if !errorlevel! equ 0 (
        echo %GREEN%  [OK]%RESET% Redis stopped
    ) else (
        echo %YELLOW%  [INFO]%RESET% Redis was not running
    )

    echo %CYAN%  Stopping PostgreSQL...%RESET%
    net stop postgresql-x64-16 >nul 2>&1
    if !errorlevel! equ 0 (
        echo %GREEN%  [OK]%RESET% PostgreSQL stopped
    ) else (
        echo %YELLOW%  [INFO]%RESET% PostgreSQL was not running
    )
) else (
    echo %YELLOW%  [INFO]%RESET% Infrastructure left running
)

REM ------------------------------------------------------------
REM 4. VERIFICATION
REM ------------------------------------------------------------
echo.
echo %CYAN%[STEP]%RESET% Verifying shutdown...

echo %CYAN%  Checking ports...%RESET%
netstat -an | findstr ":8000 " >nul
if !errorlevel! equ 0 (
    echo %RED%  [WARN]%RESET% Port 8000 still in use
) else (
    echo %GREEN%  [OK]%RESET% Port 8000 free
)

netstat -an | findstr ":8501 " >nul
if !errorlevel! equ 0 (
    echo %RED%  [WARN]%RESET% Port 8501 still in use
) else (
    echo %GREEN%  [OK]%RESET% Port 8501 free
)

netstat -an | findstr ":6379 " >nul
if !errorlevel! equ 0 (
    echo %YELLOW%  [INFO]%RESET% Redis still running on 6379
) else (
    echo %GREEN%  [OK]%RESET% Redis port 6379 free
)

netstat -an | findstr ":5432 " >nul
if !errorlevel! equ 0 (
    echo %YELLOW%  [INFO]%RESET% PostgreSQL still running on 5432
) else (
    echo %GREEN%  [OK]%RESET% PostgreSQL port 5432 free
)

REM ------------------------------------------------------------
REM 5. CLEANUP
REM ------------------------------------------------------------
echo.
echo %CYAN%[STEP]%RESET% Cleaning up temporary files...
del /q logfile >nul 2>&1
del /q *.tmp >nul 2>&1
echo %GREEN%  [OK]%RESET% Cleanup complete

REM ------------------------------------------------------------
REM 6. COMPLETE
REM ------------------------------------------------------------
echo.
echo %RED%============================================================%RESET%
echo %RED%  ELITE AUTONOMOUS QUANTUM TRADING SYSTEM - OFFLINE%RESET%
echo %RED%============================================================%RESET%
echo.
echo %GREEN%  All services stopped gracefully%RESET%
echo %GREEN%  System ready for next startup with RUN.bat%RESET%
echo.
pause