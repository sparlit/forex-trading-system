@echo off
:: Simple wrapper to invoke the EAQTS start‑up script
:: Allows the user to run `eaqts` from the repository root.

call "%~dp0scripts\windows\eaqts.bat" %*
