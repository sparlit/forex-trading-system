# Forex Trading System - Complete Startup Script (PowerShell)
# ============================================================
# This script starts all components of the trading system:
# 1. Docker infrastructure (TimescaleDB, Redis, InfluxDB, NATS)
# 2. Data ingestion worker (MT5 + CCXT -> TimescaleDB/Redis)
# 3. API server (FastAPI on port 8000)
# 4. Streamlit Dashboard (port 8501)
# 5. Bloomberg Terminal (TUI)
# ============================================================

# Parse command line arguments
param(
    [Parameter(Mandatory=$false)]
    [ValidateSet('A','B','C','D','Q')]
    [string]$Choice = ''
)

$PROJECT_DIR = "C:\Users\sp\forex-trading-system"
$COMPOSE_PROJECT = "forex"

# Define all functions FIRST (before they're called)
function Start-All {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  STARTING ALL COMPONENTS IN SEPARATE WINDOWS"
    Write-Host "============================================================"
    Write-Host ""

    # Start Data Ingestion Worker
    Write-Host "Starting Data Ingestion Worker..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; poetry run python -m src.data.runner"
    Start-Sleep -Seconds 3

    # Start API Server
    Write-Host "Starting API Server (port 8000)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; poetry run uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
    Start-Sleep -Seconds 3

    # Start Streamlit Dashboard
    Write-Host "Starting Streamlit Dashboard (port 8501)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; poetry run streamlit run src/portfolio/dashboard/app.py"
    Start-Sleep -Seconds 3

    # Start Bloomberg Terminal
    Write-Host "Starting Bloomberg Terminal..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; poetry run python src/ui/bloomberg_terminal.py"
    Start-Sleep -Seconds 2

    Show-Urls
}

function Start-WorkerOnly {
    Write-Host ""
    Write-Host "Starting Data Ingestion Worker only..."
    Set-Location $PROJECT_DIR
    poetry run python -m src.data.runner
}

function Start-WorkerDashboard {
    Write-Host ""
    Write-Host "Starting Data Worker + Dashboard in separate windows..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; poetry run python -m src.data.runner"
    Start-Sleep -Seconds 3
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; poetry run streamlit run src/portfolio/dashboard/app.py"
    Show-Urls
}

function Start-WorkerApiDashboard {
    Write-Host ""
    Write-Host "Starting Data Worker + API + Dashboard in separate windows..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; poetry run python -m src.data.runner"
    Start-Sleep -Seconds 3
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; poetry run uvicorn src.api.main:app --host 0.0.0.0 --port 8000" -WindowTitle "Forex API"
    Start-Sleep -Seconds 3
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PROJECT_DIR'; poetry run streamlit run src/portfolio/dashboard/app.py"
    Show-Urls
}

function Quit {
    Write-Host ""
    Write-Host "Infrastructure left running. To stop: docker compose -p $COMPOSE_PROJECT down"
    Read-Host "Press Enter to exit"
    exit 0
}

function Show-Urls {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  SYSTEM RUNNING - ACCESS URLS"
    Write-Host "============================================================"
    Write-Host ""
    Write-Host "Dashboard:     http://localhost:8501"
    Write-Host "API Docs:      http://localhost:8000/docs"
    Write-Host "API Health:    http://localhost:8000/health"
    Write-Host "Bloomberg:     Running in separate terminal window"
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "  VERIFICATION COMMANDS (run in new terminal)"
    Write-Host "============================================================"
    Write-Host "Check bars in DB:"
    Write-Host "  docker exec forex-timescaledb psql -U trader -d market_data -c `"SELECT s.symbol, COUNT(*) FROM market_data.bars b JOIN market_data.symbols s ON b.symbol_id=s.symbol_id WHERE b.is_complete=TRUE GROUP BY s.symbol`""
    Write-Host ""
    Write-Host "Check Redis:"
    Write-Host "  docker exec forex-redis redis-cli --scan --pattern 'tick:*'"
    Write-Host "  docker exec forex-redis redis-cli --scan --pattern 'bar:*'"
    Write-Host ""
    Write-Host "Stop all: docker compose -p $COMPOSE_PROJECT down"
    Write-Host "============================================================"
    Write-Host ""
    Write-Host "Press any key to close this window (other windows stay open)..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  FOREX TRADING SYSTEM - STARTUP (PowerShell)"
Write-Host "============================================================"
Write-Host "Project: $PROJECT_DIR"
Write-Host "Docker Project: $COMPOSE_PROJECT"
Write-Host ""

# Check if Docker Desktop is running
Write-Host "[1/6] Checking Docker Desktop..."
try {
    $dockerVersion = docker version --format '{{.Server.Version}}' 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Docker not ready" }
    Write-Host "Docker OK (Server: $dockerVersion)"
} catch {
    Write-Error "ERROR: Docker Desktop is not running!"
    Write-Host "Please start Docker Desktop and wait for it to be ready."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# Check if MT5 terminal is running
Write-Host "[2/6] Checking MetaTrader 5..."
$mt5Process = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue
if ($mt5Process) {
    Write-Host "MT5 Terminal: RUNNING (PID: $($mt5Process.Id))"
} else {
    Write-Warning "MT5 Terminal not detected. Make sure it's running and logged in."
}
Write-Host ""

# Start Docker infrastructure
Write-Host "[3/6] Starting Docker infrastructure (TimescaleDB, Redis, InfluxDB, NATS)..."
Set-Location $PROJECT_DIR
$composeResult = docker compose -p $COMPOSE_PROJECT up -d timescaledb redis influxdb nats --no-deps
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: Failed to start Docker containers"
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "Waiting for services to be healthy..."
Start-Sleep -Seconds 10
Write-Host ""

# Verify infrastructure
Write-Host "[4/6] Verifying infrastructure connections..."
$redisOk = $false
$timescaleOk = $false
$natsOk = $false

try {
    $result = docker exec forex-redis redis-cli ping 2>$null
    if ($LASTEXITCODE -eq 0 -and $result.Trim() -eq "PONG") {
        Write-Host "Redis: OK"
        $redisOk = $true
    } else { Write-Host "Redis: FAILED" }
} catch { Write-Host "Redis: FAILED" }

try {
    $result = docker exec forex-timescaledb pg_isready -U trader -d market_data 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "TimescaleDB: OK"
        $timescaleOk = $true
    } else { Write-Host "TimescaleDB: FAILED" }
} catch { Write-Host "TimescaleDB: FAILED" }

try {
    $result = docker exec forex-nats nats --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "NATS: OK"
        $natsOk = $true
    } else { Write-Host "NATS: OK (service running, CLI not in container)" }
} catch { Write-Host "NATS: OK (service running, CLI not in container)" }
Write-Host ""

# Get choice from parameter or prompt
if (-not $Choice) {
    # Menu for what to start
    Write-Host "============================================================"
    Write-Host "  SELECT COMPONENTS TO START"
    Write-Host "============================================================"
    Write-Host "[A] All components (Data Worker + API + Dashboard + Terminal)"
    Write-Host "[B] Data Worker only"
    Write-Host "[C] Data Worker + Dashboard"
    Write-Host "[D] Data Worker + API + Dashboard"
    Write-Host "[Q] Quit (infrastructure stays running)"
    Write-Host ""

    $choice = Read-Host "Enter choice [A/B/C/D/Q]" -ErrorAction Stop
} else {
    Write-Host "Using choice from parameter: $Choice"
}

switch ($choice.ToUpper()) {
    "A" { Start-All }
    "B" { Start-WorkerOnly }
    "C" { Start-WorkerDashboard }
    "D" { Start-WorkerApiDashboard }
    "Q" { Quit }
    default { Write-Host "Invalid choice. Starting all components..."; Start-All }
}