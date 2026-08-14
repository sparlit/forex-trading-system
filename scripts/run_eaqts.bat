@echo off
:: ------------------------------------------------------------
:: Windows batch script to set up and start EAQTS V2.4
:: ------------------------------------------------------------

setlocal EnableDelayedExpansion

:: Helper functions
:info
    echo [INFO] %~1
    goto :eof

:err
    echo [ERROR] %~1
    exit /b 1

:: 1. Ensure Scoop is installed
where scoop >nul 2>&1
if errorlevel 1 (
    call :info "Installing Scoop..."
    powershell -Command "iwr -useb get.scoop.sh | iex"
    if errorlevel 1 call :err "Failed to install Scoop"
    call :info "Adding extras bucket"
    scoop bucket add extras
) else (
    call :info "Scoop already installed"
)

:: 2. Install Python and Poetry if missing
where python >nul 2>&1
if errorlevel 1 (
    call :info "Installing Python via Scoop..."
    scoop install python
) else (
    call :info "Python already present"
)

where poetry >nul 2>&1
if errorlevel 1 (
    call :info "Installing Poetry via Scoop..."
    scoop install poetry
) else (
    call :info "Poetry already present"
)

:: 3. Change to project root (script is in scripts folder)
cd /d "%~dp0.."

:: 4. Install Python dependencies
call :info "Installing Python dependencies via Poetry..."
poetry install --with dev,ml,viz,trading
if errorlevel 1 call :err "Poetry install failed"

:: 5. Prepare .env file
if not exist .env (
    call :info "Creating .env from .env.example"
    copy .env.example .env >nul
    echo # Edit .env with your MT5, API keys, DB URLs>>.env
) else (
    call :info ".env already exists"
)

:: 6. Initialise the system (creates DB, starts Prometheus, runs quick test)
call :info "Running eaqts-cli init..."
poetry run python scripts/eaqts_cli.py init
if errorlevel 1 call :err "eaqts-cli init failed"

:: 7. Start the trading loop
call :info "Starting EAQTS trading loop..."
poetry run python scripts/eaqts_cli.py start
if errorlevel 1 call :err "Failed to start trading loop"

call :info "EAQTS is now running. Use 'eaqts-cli status' or 'eaqts-cli stop' to manage it."
exit /b 0
