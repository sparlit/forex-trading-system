<#PSScriptInfo
.VERSION 1.0.0
.GUID 1a2b3c4d-5e6f-7g8h-9i0j-k1l2m3n4o5p6
.AUTHOR Forex Trading System
.COPYRIGHT (c) 2024
.TAGS forex, trading, installer, infrastructure
.PROJECTURI https://github.com/your-repo/forex-trading-system
.LICENSEURI MIT
.RELEASENOTES Initial release - one-command installer for Forex Trading System
#>

<#
.SYNOPSIS
    Forex Trading System - One-Command Installer & Launcher

.DESCRIPTION
    Installs and configures all infrastructure services (PostgreSQL/TimescaleDB, Redis, InfluxDB, NATS, Prometheus, Grafana)
    using Scoop package manager, then starts the entire trading system stack.

.PARAMETER InstallOnly
    Only install infrastructure, don't start the application

.PARAMETER StartOnly
    Skip installation, start services and application only (assumes already installed)

.PARAMETER NoServices
    Don't start infrastructure services, only start the trading application

.PARAMETER Force
    Force reinstallation of all components

.PARAMETER Verbose
    Show detailed output

.EXAMPLE
    .\install.ps1
    # Full install + start everything

.EXAMPLE
    .\install.ps1 -StartOnly
    # Start everything (assumes already installed)

.EXAMPLE
    .\install.ps1 -InstallOnly
    # Only install infrastructure

.EXAMPLE
    .\install.ps1 -NoServices
    # Start only the trading app (services already running externally)
#>

[CmdletBinding(DefaultParameterSetName='Full')]
param(
    [Parameter(ParameterSetName='InstallOnly')]
    [switch]$InstallOnly,

    [Parameter(ParameterSetName='StartOnly')]
    [switch]$StartOnly,

    [Parameter(ParameterSetName='Full')]
    [switch]$NoServices,

    [switch]$Force
)

# ============================================================
# CONFIGURATION
# ============================================================
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectDir = Resolve-Path $ScriptDir

$Services = @(
    @{ Name = 'postgresql'; Port = 5432; HealthUrl = '' },
    @{ Name = 'redis'; Port = 6379; HealthUrl = '' },
    @{ Name = 'influxdb'; Port = 8181; HealthUrl = 'http://localhost:8181/health' },
    @{ Name = 'nats-server'; Port = 4222; HealthUrl = 'http://localhost:8222/healthz' },
    @{ Name = 'prometheus'; Port = 9090; HealthUrl = 'http://localhost:9090/-/healthy' },
    @{ Name = 'grafana'; Port = 3000; HealthUrl = 'http://localhost:3000/api/health' }
)

$AppServices = @(
    @{ Name = 'API'; Command = 'poetry run python -m src.api.main'; Port = 8000; Dir = $ProjectDir },
    @{ Name = 'Dashboard'; Command = 'poetry run streamlit run src/portfolio/dashboard/app.py --server.port 8501 --server.address 0.0.0.0'; Port = 8501; Dir = $ProjectDir }
)

$ScoopPackages = @('postgresql', 'redis', 'influxdb', 'nats-server', 'prometheus', 'grafana')

# ============================================================
# HELPER FUNCTIONS
# ============================================================
function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $timestamp = Get-Date -Format 'HH:mm:ss'
    $color = switch ($Level) {
        'ERROR' { 'Red' }
        'WARN'  { 'Yellow' }
        'SUCCESS' { 'Green' }
        'INFO'  { 'Cyan' }
        default { 'White' }
    }
    Write-Host "[$timestamp] [$Level] $Message" -ForegroundColor $color
}

function Test-Command {
    param([string]$Command)
    try {
        Get-Command $Command -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Test-Port {
    param([int]$Port, [string]$TargetHost = 'localhost')
    try {
        $socket = New-Object System.Net.Sockets.TcpClient
        $result = $socket.BeginConnect($TargetHost, $Port, $null, $null)
        $success = $result.AsyncWaitHandle.WaitOne(2000)
        $socket.Close()
        return $success
    } catch {
        return $false
    }
}

function Test-HealthEndpoint {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-For-Service {
    param([string]$Name, [int]$Port, [string]$HealthUrl = '', [int]$Timeout = 60)
    Write-Log "Waiting for $Name on port $Port..." 'INFO'
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($stopwatch.Elapsed.TotalSeconds -lt $Timeout) {
        $portOk = Test-Port -Port $Port
        $healthOk = $true
        if ($HealthUrl) { $healthOk = Test-HealthEndpoint -Url $HealthUrl }
        if ($portOk -and $healthOk) {
            Write-Log "$Name is ready!" 'SUCCESS'
            return $true
        }
        Start-Sleep -Seconds 2
    }
    Write-Log "$Name failed to start within ${Timeout}s" 'ERROR'
    return $false
}

function Install-Scoop {
    if (Test-Command 'scoop') {
        Write-Log "Scoop already installed" 'SUCCESS'
        return $true
    }
    Write-Log "Installing Scoop package manager..." 'INFO'
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
    try {
        irm get.scoop.sh | iex
        Write-Log "Scoop installed successfully" 'SUCCESS'
        return $true
    } catch {
        Write-Log "Failed to install Scoop: $($_.Exception.Message)" 'ERROR'
        return $false
    }
}

function Install-Infrastructure {
    Write-Log "=== INSTALLING INFRASTRUCTURE SERVICES ===" 'INFO'

    if (-not (Install-Scoop)) { return $false }

    Write-Log "Adding extras bucket..." 'INFO'
    scoop bucket add extras 2>$null | Out-Null

    foreach ($pkg in $ScoopPackages) {
        if ($Force -or -not (scoop list | Select-String $pkg)) {
            Write-Log "Installing $pkg..." 'INFO'
            try {
                scoop install $pkg
                Write-Log "$pkg installed" 'SUCCESS'
            } catch {
                $err = $_.Exception.Message
                Write-Log "Failed to install $pkg - $err" 'ERROR'
                return $false
            }
        } else {
            Write-Log "$pkg already installed" 'SUCCESS'
        }
    }

    # Hold packages to prevent breaking updates
    Write-Log "Pinning packages to prevent breaking updates..." 'INFO'
    foreach ($pkg in $ScoopPackages) {
        scoop hold $pkg 2>$null | Out-Null
    }

    # Initialize TimescaleDB extension
    Write-Log "Configuring TimescaleDB extension..." 'INFO'
    try {
        $pgBin = "$env:USERPROFILE\scoop\apps\postgresql\current\bin\psql.exe"
        if (Test-Path $pgBin) {
            & $pgBin -U postgres -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 2>$null
            Write-Log "TimescaleDB extension enabled" 'SUCCESS'
        }
    } catch {
        Write-Log "TimescaleDB extension setup (run manually if needed): CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 'WARN'
    }

    return $true
}

function Start-Infrastructure {
    Write-Log "=== STARTING INFRASTRUCTURE SERVICES ===" 'INFO'

    # PostgreSQL
    Write-Log "Starting postgresql..." 'INFO'
    try {
        $pgCtl = "$env:USERPROFILE\scoop\apps\postgresql\current\bin\pg_ctl.exe"
        $pgData = "$env:USERPROFILE\scoop\apps\postgresql\current\data"
        if (Test-Path $pgCtl) {
            Start-Process -FilePath $pgCtl -ArgumentList "-D `"$pgData`" -l logfile start" -WindowStyle Hidden
            Write-Log "postgresql started" 'SUCCESS'
        }
    } catch {
        $err = $_.Exception.Message
        Write-Log "Failed to start postgresql: $err" 'ERROR'
    }

    # Redis
    Write-Log "Starting redis..." 'INFO'
    try {
        $redisExe = "$env:USERPROFILE\scoop\apps\redis\current\redis-server.exe"
        if (Test-Path $redisExe) {
            Start-Process -FilePath $redisExe -WindowStyle Hidden
            Write-Log "redis started" 'SUCCESS'
        }
    } catch {
        $err = $_.Exception.Message
        Write-Log "Failed to start redis: $err" 'ERROR'
    }

    # InfluxDB
    Write-Log "Starting influxdb..." 'INFO'
    try {
        $influxExe = "$env:ProgramData\scoop\apps\influxdb\current\influxdb3.exe"
        if (Test-Path $influxExe) {
            Start-Process -FilePath $influxExe -ArgumentList "serve --node-id node1 --object-store memory --data-dir $env:USERPROFILE\scoop\persist\influxdb\data --disable-authz health" -WindowStyle Hidden
            Write-Log "influxdb started" 'SUCCESS'
        }
    } catch {
        $err = $_.Exception.Message
        Write-Log "Failed to start influxdb: $err" 'ERROR'
    }

        # NATS
        Write-Log "Starting nats-server..." 'INFO'
        try {
            $natsExe = "$env:ProgramData\scoop\apps\nats-server\current\nats-server.exe"
            if (Test-Path $natsExe) {
                # Use Start-Process with NoNewWindow to keep it running
                Start-Process -FilePath $natsExe -ArgumentList "-js -m 8222" -WindowStyle Hidden -PassThru | Out-Null
                Start-Sleep -Seconds 3
                Write-Log "nats-server started" 'SUCCESS'
            }
        } catch {
            $err = $_.Exception.Message
            Write-Log "Failed to start nats-server: $err" 'ERROR'
        }

        # Prometheus
        Write-Log "Starting prometheus..." 'INFO'
        try {
            $promExe = "$env:ProgramData\scoop\apps\prometheus\current\prometheus.exe"
            $promConfig = "$env:ProgramData\scoop\apps\prometheus\current\prometheus.yml"
            $promData = "$env:USERPROFILE\scoop\persist\prometheus\data"
            if (Test-Path $promExe) {
                $arg = "--config.file=`"$promConfig`" --storage.tsdb.path=`"$promData`" --web.enable-lifecycle"
                Start-Process -FilePath $promExe -ArgumentList $arg -WindowStyle Hidden -PassThru | Out-Null
                Write-Log "prometheus started" 'SUCCESS'
            }
        } catch {
            $err = $_.Exception.Message
            Write-Log "Failed to start prometheus: $err" 'ERROR'
        }

        # Grafana
        Write-Log "Starting grafana..." 'INFO'
        try {
            $grafanaExe = "$env:ProgramData\scoop\apps\grafana\current\bin\grafana.exe"
            $grafanaHome = "$env:ProgramData\scoop\apps\grafana\current"
            if (Test-Path $grafanaExe) {
                Start-Process -FilePath $grafanaExe -ArgumentList "server --homepath=`"$grafanaHome`"" -WindowStyle Hidden -PassThru | Out-Null
                Write-Log "grafana started" 'SUCCESS'
            }
        } catch {
            $err = $_.Exception.Message
            Write-Log "Failed to start grafana: $err" 'ERROR'
        }

        # Wait for all services to be healthy
    Write-Log "Waiting for services to become healthy..." 'INFO'
    $allHealthy = $true
    foreach ($svc in $Services) {
        if (-not (Wait-For-Service -Name $svc.Name -Port $svc.Port -HealthUrl $svc.HealthUrl -Timeout 60)) {
            $allHealthy = $false
        }
    }

    if ($allHealthy) {
        Write-Log "All infrastructure services are healthy!" 'SUCCESS'
    }
    return $allHealthy
}

function Stop-Infrastructure {
    Write-Log "Stopping infrastructure services..." 'INFO'
    foreach ($svc in $Services) {
        try {
            $procs = Get-Process -Name $svc.Name -ErrorAction SilentlyContinue
            foreach ($p in $procs) { Stop-Process -Id $p.Id -Force }
            Write-Log "Stopped $($svc.Name)" 'INFO'
        } catch { }
    }
}

function Configure-Environment {
    Write-Log "Configuring environment variables..." 'INFO'
    $envFile = Join-Path $ProjectDir '.env'
    $secretKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 64 | ForEach-Object { [char]$_ })
    $envContent = @"
# Forex Trading System - Generated by installer
APP_NAME=forex-trading-system
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG

# Database
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_DATABASE=market_data
TIMESCALE_USER=postgres
TIMESCALE_PASSWORD=postgres
TIMESCALE_POOL_SIZE=10

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# InfluxDB
INFLUX_URL=http://localhost:8181
INFLUX_TOKEN=my-super-secret-admin-token
INFLUX_ORG=trading
INFLUX_BUCKET=metrics

# NATS
NATS_SERVERS=["nats://localhost:4222"]

# API
API_HOST=0.0.0.0
API_PORT=8000

# Dashboard
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8501

# Secrets
SECRET_KEY=$secretKey
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60
"@
    $envContent | Out-File -FilePath $envFile -Encoding utf8
    Write-Log "Environment file created: $envFile" 'SUCCESS'
}

function Start-TradingApp {
    Write-Log "=== STARTING TRADING APPLICATION ===" 'INFO'

    # Ensure dependencies
    Write-Log "Installing Python dependencies..." 'INFO'
    Set-Location $ProjectDir
    poetry install --no-interaction 2>&1 | Out-Null

    # Start API
    Write-Log "Starting API server on port 8000..." 'INFO'
    $apiProcess = Start-Process -FilePath "poetry" -ArgumentList "run python -m src.api.main" -WorkingDirectory $ProjectDir -WindowStyle Normal -PassThru

    # Wait for API
    Start-Sleep -Seconds 5
    if (Test-Port -Port 8000) {
        Write-Log "API server running on http://localhost:8000" 'SUCCESS'
    } else {
        Write-Log "API server may still be starting..." 'WARN'
    }

    # Start Dashboard
    Write-Log "Starting Dashboard on port 8501..." 'INFO'
    $dashProcess = Start-Process -FilePath "poetry" -ArgumentList "run streamlit run src/portfolio/dashboard/app.py --server.port 8501 --server.address 0.0.0.0" -WorkingDirectory $ProjectDir -WindowStyle Normal -PassThru

    Start-Sleep -Seconds 5
    if (Test-Port -Port 8501) {
        Write-Log "Dashboard running on http://localhost:8501" 'SUCCESS'
    } else {
        Write-Log "Dashboard may still be starting..." 'WARN'
    }

    return @($apiProcess, $dashProcess)
}

function Show-Status {
    Write-Log "=== SYSTEM STATUS ===" 'INFO'
    Write-Host ""
    Write-Host "Infrastructure Services:" -ForegroundColor Cyan
    foreach ($svc in $Services) {
        $portOk = Test-Port -Port $svc.Port
        $status = if ($portOk) { "RUNNING" } else { "STOPPED" }
        $color = if ($portOk) { 'Green' } else { 'Red' }
        Write-Host "  $($svc.Name): $status (port $($svc.Port))" -ForegroundColor $color
    }
    Write-Host ""
    Write-Host "Application Services:" -ForegroundColor Cyan
    foreach ($app in $AppServices) {
        $portOk = Test-Port -Port $app.Port
        $status = if ($portOk) { "RUNNING" } else { "STOPPED" }
        $color = if ($portOk) { 'Green' } else { 'Red' }
        Write-Host "  $($app.Name): $status (port $($app.Port))" -ForegroundColor $color
    }
    Write-Host ""
    Write-Host "Access URLs:" -ForegroundColor Cyan
    Write-Host "  API (Swagger):     http://localhost:8000/docs" -ForegroundColor Yellow
    Write-Host "  API (Health):      http://localhost:8000/health" -ForegroundColor Yellow
    Write-Host "  Dashboard:         http://localhost:8501" -ForegroundColor Yellow
    Write-Host "  Prometheus:        http://localhost:9090" -ForegroundColor Yellow
    Write-Host "  Grafana:           http://localhost:3000 (admin/admin)" -ForegroundColor Yellow
    Write-Host "  NATS Monitor:      http://localhost:8222" -ForegroundColor Yellow
    Write-Host "  InfluxDB:          http://localhost:8086" -ForegroundColor Yellow
}

# ============================================================
# MAIN EXECUTION
# ============================================================
try {
    Write-Log "============================================================" 'INFO'
    Write-Log "  FOREX TRADING SYSTEM - ONE-COMMAND INSTALLER" 'INFO'
    Write-Log "============================================================" 'INFO'

    if ($InstallOnly) {
        # INSTALL ONLY
        Configure-Environment
        Install-Infrastructure
        Write-Log "Installation complete! Run without -InstallOnly to start the system." 'SUCCESS'
        exit 0
    }

    if ($StartOnly) {
        # START ONLY (assume installed)
        Configure-Environment
        if (-not $NoServices) {
            Start-Infrastructure
        }
        Start-TradingApp
        Show-Status
        Write-Log "System running! Press Ctrl+C to stop..." 'INFO'
        # Keep script alive
        while ($true) { Start-Sleep -Seconds 10 }
        exit 0
    }

    # FULL INSTALL + START
    Configure-Environment
    Install-Infrastructure
    Start-Infrastructure
    Start-TradingApp
    Show-Status

    Write-Log "============================================================" 'INFO'
    Write-Log "  FOREX TRADING SYSTEM IS RUNNING!" 'SUCCESS'
    Write-Log "  Press Ctrl+C to stop all services" 'INFO'
    Write-Log "============================================================" 'INFO'

    # Keep running until Ctrl+C
    while ($true) { Start-Sleep -Seconds 10 }

} catch {
    Write-Log "Fatal error: $($_.Exception.Message)" 'ERROR'
    if ($Verbose) { Write-Error $_ }
    exit 1
} finally {
    # Cleanup on exit
    if (-not $NoServices -and -not $InstallOnly -and -not $StartOnly) {
        Write-Log "Shutting down..." 'INFO'
        Stop-Infrastructure
    }
}