@echo off
:: Simple wrapper to invoke the EAQTS CLI directly.
:: Ensure we are in the repository root (where this .cmd resides).
cd /d "%~dp0"

:: Forward all arguments to the Python CLI script.
python scripts/eaqts_cli.py %*

:: End of wrapper