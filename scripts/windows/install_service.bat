@echo off
:: Install EAQTS trading loop as a Windows service using nssm (the Non‑Sucking Service Manager).
:: Requires nssm to be in the system PATH. If nssm is unavailable, the script aborts with instructions.
setlocal EnableDelayedExpansion

set SERVICE_NAME=eaqts
set SERVICE_DESC=EAQTS Trading Loop Service

:: Resolve the path to the root-level eaqts.cmd wrapper (one directory up from this script).
set ROOT_DIR=%~dp0..\
if not exist "%ROOT_DIR%\eaqts.cmd" (
    echo [ERROR] eaqts.cmd not found at "%ROOT_DIR%".
    exit /b 1
)

:: Check for nssm executable.
where nssm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] nssm not found in PATH.
    echo Install nssm (https://nssm.cc/download) and ensure its directory is in your PATH,
    echo or use Windows Task Scheduler to run eaqts.cmd manually.
    exit /b 1
)

:: Install the service.
echo Installing service "%SERVICE_NAME%" …
nssm install %SERVICE_NAME% "%ROOT_DIR%\eaqts.cmd" start
if errorlevel 1 (
    echo [ERROR] nssm failed to install the service.
    exit /b 1
)

:: Set display name and description.
nssm set %SERVICE_NAME% DisplayName "%SERVICE_NAME%"
nssm set %SERVICE_NAME% Description "%SERVICE_DESC%"

:: Start the service.
nssm start %SERVICE_NAME%
if errorlevel 1 (
    echo [ERROR] Failed to start the service.
    exit /b 1
)

echo Service "%SERVICE_NAME%" installed and started successfully.
endlocal