<#PSScriptInfo
.VERSION 1.0.0
.GUID 1a2b3c4d-5e6f-7g8h-9i0j-k1l2m3n4o5p6
.AUTHOR Forex Trading System
.COPYRIGHT (c) 2024
.TAGS forex, trading, service, nssm, autonomous, windows-service
.PROJECTURI https://github.com/your-repo/forex-trading-system
.LICENSEURI MIT
.RELEASENOTES Install Forex Trading System as Windows Services for 24/7 autonomous operation
#>

<#
.SYNOPSIS
    Install Forex Trading System as Windows Services (NSSM) for 24/7 autonomous operation

.DESCRIPTION
    This script installs all infrastructure + application components as Windows Services using NSSM (Non-Sucking Service Manager).
    Services start automatically on boot, restart on failure, and run completely in the background - no terminal required.

.PARAMETER Install
    Install all services (default)

.PARAMETER Uninstall
    Remove all services

.PARAMETER Start
    Start all installed services

.PARAMETER Stop
    Stop all services

.PARAMETER Restart
    Restart all services

.PARAMETER Status
    Show status of all services

.EXAMPLE
    .\install-services.ps1 -Install
    # Install all as Windows Services

.EXAMPLE
    .\install-services.ps1 -Start
    # Start all services

.EXAMPLE
    .\install-services.ps1 -Status
    # Check status
#>

[CmdletBinding(DefaultParameterSetName='Install')]
param(
    [Parameter(ParameterSetName='Install')]
    [switch]$Install,

    [Parameter(ParameterSetName='Uninstall')]
    [switch]$Uninstall,

    [Parameter(ParameterSetName='Start')]
    [switch]$Start,

    [Parameter(ParameterSetName='Stop')]
    [switch]$Stop,

    [Parameter(ParameterSetName='Restart')]
    [switch]$Restart,

    [Parameter(ParameterSetName='Status')]
    [switch]$Status
)

# ============================================================
# CONFIGURATION
# ============================================================
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectDir = Resolve-Path $ScriptDir
$NssmPath = "$env:ProgramData\scoop\apps\nssm\current\nssm.exe"
$SvcPrefix = "ForexTrading"

# PostgreSQL data directory
$PgDataDir = "$env:ProgramData\scoop\persist\postgresql\data"
# Prometheus config and data
$PromConfig = "$env:ProgramData\scoop\apps\prometheus\current\prometheus.yml"
$PromData = "$env:USERPROFILE\scoop\persist\prometheus\data"
# Grafana home
$GrafanaHome = "$env:ProgramData\scoop\apps\grafana\current"
# InfluxDB data
$InfluxData = "$env:USERPROFILE\scoop\persist\influxdb\data"

$Services = @(
    @{
        Name = "$SvcPrefix-PostgreSQL"
        DisplayName = "Forex Trading - PostgreSQL/TimescaleDB"
        Description = "PostgreSQL database with TimescaleDB extension for market data"
        Exe = "$env:ProgramData\scoop\apps\postgresql\current\bin\postgres.exe"
        Args = "-D `"$PgDataDir`""
        Dir = "$env:ProgramData\scoop\apps\postgresql\current\bin"
        Depends = @()
    },
    @{
        Name = "$SvcPrefix-Redis"
        DisplayName = "Forex Trading - Redis"
        Description = "Redis in-memory cache and pub/sub"
        Exe = "$env:ProgramData\scoop\apps\redis\current\redis-server.exe"
        Args = "--daemonize no"
        Dir = "$env:ProgramData\scoop\apps\redis\current"
        Depends = @()
    },
    @{
        Name = "$SvcPrefix-InfluxDB"
        DisplayName = "Forex Trading - InfluxDB"
        Description = "InfluxDB 3 time-series metrics database"
        Exe = "$env:ProgramData\scoop\apps\influxdb\current\influxdb3.exe"
        Args = "serve --node-id node1 --object-store memory --data-dir $InfluxData --disable-authz health"
        Dir = "$env:ProgramData\scoop\apps\influxdb\current"
        Depends = @()
    },
    @{
        Name = "$SvcPrefix-NATS"
        DisplayName = "Forex Trading - NATS Server"
        Description = "NATS message broker with JetStream for event bus"
        Exe = "$env:ProgramData\scoop\apps\nats-server\current\nats-server.exe"
        Args = "-js -m 8222"
        Dir = "$env:ProgramData\scoop\apps\nats-server\current"
        Depends = @()
    },
    @{
        Name = "$SvcPrefix-Prometheus"
        DisplayName = "Forex Trading - Prometheus"
        Description = "Prometheus metrics collection and monitoring"
        Exe = "$env:ProgramData\scoop\apps\prometheus\current\prometheus.exe"
        Args = "--config.file=`"$PromConfig`" --storage.tsdb.path=`"$PromData`" --web.enable-lifecycle"
        Dir = "$env:ProgramData\scoop\apps\prometheus\current"
        Depends = @("$SvcPrefix-NATS")
    },
    @{
        Name = "$SvcPrefix-Grafana"
        DisplayName = "Forex Trading - Grafana"
        Description = "Grafana visualization and dashboards"
        Exe = "$env:ProgramData\scoop\apps\grafana\current\bin\grafana.exe"
        Args = "server --homepath=`"$GrafanaHome`""
        Dir = "$env:ProgramData\scoop\apps\grafana\current\bin"
        Depends = @("$SvcPrefix-Prometheus", "$SvcPrefix-InfluxDB")
    },
    @{
        Name = "$SvcPrefix-API"
        DisplayName = "Forex Trading - API Server"
        Description = "FastAPI REST API + WebSocket server"
        Exe = "$env:USERPROFILE\.poetry\bin\poetry.exe"
        Args = "run python -m src.api.main"
        Dir = $ProjectDir
        Depends = @("$SvcPrefix-PostgreSQL", "$SvcPrefix-Redis", "$SvcPrefix-NATS")
        Env = @{
            PYTHONPATH = $ProjectDir
        }
    },
    @{
        Name = "$SvcPrefix-Dashboard"
        DisplayName = "Forex Trading - Dashboard"
        Description = "Streamlit real-time trading dashboard"
        Exe = "$env:USERPROFILE\.poetry\bin\poetry.exe"
        Args = "run streamlit run src/portfolio/dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true"
        Dir = $ProjectDir
        Depends = @("$SvcPrefix-API")
        Env = @{
            PYTHONPATH = $ProjectDir
        }
    }
)

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

function Ensure-Nssm {
    if (-not (Test-Path $NssmPath)) {
        Write-Log "Installing NSSM via Scoop..." 'INFO'
        scoop install nssm
    }
    if (-not (Test-Path $NssmPath)) {
        Write-Log "NSSM not found at $NssmPath" 'ERROR'
        return $false
    }
    return $true
}

function Install-Service {
    param($svc)
    Write-Log "Installing service: $($svc.Name)..." 'INFO'
    
    # Stop if exists
    & $NssmPath stop $svc.Name 2>$null | Out-Null
    & $NssmPath remove $svc.Name confirm 2>$null | Out-Null
    
    # Install
    & $NssmPath install $svc.Name $svc.Exe $svc.Args
    if ($LASTEXITCODE -ne 0) {
        Write-Log "Failed to install $($svc.Name)" 'ERROR'
        return $false
    }
    
    # Configure
    & $NssmPath set $svc.Name AppDirectory $svc.Dir
    & $NssmPath set $svc.Name DisplayName $svc.DisplayName
    & $NssmPath set $svc.Name Description $svc.Description
    & $NssmPath set $svc.Name Start SERVICE_AUTO_START
    & $NssmPath set $svc.Name AppStdout "$env:ProgramData\$($svc.Name).log"
    & $NssmPath set $svc.Name AppStderr "$env:ProgramData\$($svc.Name)-error.log"
    & $NssmPath set $svc.Name AppRotateFiles 1
    & $NssmPath set $svc.Name AppRotateBytes 10485760
    
    # Dependencies
    if ($svc.Depends.Count -gt 0) {
        & $NssmPath set $svc.Name DependOnService $svc.Depends
    }
    
    # Environment variables
    if ($svc.Env) {
        foreach ($key in $svc.Env.Keys) {
            & $NssmPath set $svc.Name AppEnvironmentExtra $key=$($svc.Env[$key])
        }
    }
    
    # Recovery: restart on failure
    & $NssmPath set $svc.Name AppExit Default Restart
    & $NssmPath set $svc.Name AppThrottle 5000
    & $NssmPath set $svc.Name AppRestartDelay 10000
    
    Write-Log "Service $($svc.Name) installed successfully" 'SUCCESS'
    return $true
}

function Uninstall-Service {
    param([string]$Name)
    Write-Log "Uninstalling service: $Name..." 'INFO'
    & $NssmPath stop $Name 2>$null | Out-Null
    & $NssmPath remove $Name confirm 2>$null | Out-Null
    Write-Log "Service $Name uninstalled" 'SUCCESS'
}

function Start-ServiceWrapper {
    param([string]$Name, [string]$DisplayName)
    Write-Log "Starting $DisplayName..." 'INFO'
    & $NssmPath start $Name
    if ($LASTEXITCODE -eq 0) {
        Write-Log "$DisplayName started" 'SUCCESS'
    } else {
        Write-Log "$DisplayName failed to start" 'ERROR'
    }
}

function Stop-ServiceWrapper {
    param([string]$Name, [string]$DisplayName)
    Write-Log "Stopping $DisplayName..." 'INFO'
    & $NssmPath stop $Name
    Write-Log "$DisplayName stopped" 'SUCCESS'
}

function Get-ServiceStatus {
    param([string]$Name)
    try {
        $svc = Get-Service -Name $Name -ErrorAction Stop
        $status = $svc.Status
        return $status
    } catch {
        return "NotInstalled"
    }
}

# ============================================================
# MAIN EXECUTION
# ============================================================
Write-Log "============================================================" 'INFO'
Write-Log "  FOREX TRADING SYSTEM - WINDOWS SERVICE MANAGER" 'INFO'
Write-Log "============================================================" 'INFO'

if (-not (Ensure-Nssm)) { exit 1 }

if ($Install) {
    # INSTALL ALL SERVICES
    Write-Log "=== INSTALLING ALL SERVICES ===" 'INFO'
    foreach ($svc in $Services) {
        Install-Service -svc $svc
    }
    
    Write-Log "=== ALL SERVICES INSTALLED ===" 'INFO'
    Write-Log "Services will start automatically on boot." 'INFO'
    Write-Log "Run with -Start to start them now." 'INFO'
    
} elseif ($Uninstall) {
    # UNINSTALL ALL SERVICES (reverse order)
    Write-Log "=== UNINSTALLING ALL SERVICES ===" 'INFO'
    foreach ($svc in $Services | Sort-Object { $_.Name } -Descending) {
        Uninstall-Service -Name $svc.Name
    }
    Write-Log "=== ALL SERVICES UNINSTALLED ===" 'INFO'
    
} elseif ($Start) {
    # START ALL SERVICES (dependency order)
    Write-Log "=== STARTING ALL SERVICES ===" 'INFO'
    foreach ($svc in $Services) {
        Start-ServiceWrapper -Name $svc.Name -DisplayName $svc.DisplayName
        Start-Sleep -Seconds 3
    }
    
} elseif ($Stop) {
    # STOP ALL SERVICES (reverse order)
    Write-Log "=== STOPPING ALL SERVICES ===" 'INFO'
    foreach ($svc in $Services | Sort-Object { $_.Name } -Descending) {
        Stop-ServiceWrapper -Name $svc.Name -DisplayName $svc.DisplayName
    }
    
} elseif ($Restart) {
    # RESTART ALL SERVICES
    Write-Log "=== RESTARTING ALL SERVICES ===" 'INFO'
    foreach ($svc in $Services | Sort-Object { $_.Name } -Descending) {
        Stop-ServiceWrapper -Name $svc.Name -DisplayName $svc.DisplayName
    }
    Start-Sleep -Seconds 5
    foreach ($svc in $Services) {
        Start-ServiceWrapper -Name $svc.Name -DisplayName $svc.DisplayName
        Start-Sleep -Seconds 3
    }
    
} elseif ($Status) {
    # SHOW STATUS
    Write-Log "=== SERVICE STATUS ===" 'INFO'
    Write-Host ""
    Write-Host "Infrastructure Services:" -ForegroundColor Cyan
    foreach ($svc in $Services | Where-Object { $_.Name -notlike "*API" -and $_.Name -notlike "*Dashboard" }) {
        $status = Get-ServiceStatus -Name $svc.Name
        $color = switch ($status) {
            'Running' { 'Green' }
            'Stopped' { 'Yellow' }
            default   { 'Red' }
        }
        Write-Host "  $($svc.DisplayName): $status" -ForegroundColor $color
    }
    Write-Host ""
    Write-Host "Application Services:" -ForegroundColor Cyan
    foreach ($svc in $Services | Where-Object { $_.Name -like "*API" -or $_.Name -like "*Dashboard" }) {
        $status = Get-ServiceStatus -Name $svc.Name
        $color = switch ($status) {
            'Running' { 'Green' }
            'Stopped' { 'Yellow' }
            default   { 'Red' }
        }
        Write-Host "  $($svc.DisplayName): $status" -ForegroundColor $color
    }
    Write-Host ""
}

Write-Log "Done." 'INFO'