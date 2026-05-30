@echo off
setlocal

set "ROOT=%~dp0"
set "SCRIPT=%ROOT%att-wolf-wizard.ps1"

if not exist "%SCRIPT%" (
  echo Missing wizard script: %SCRIPT%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" %*
exit /b %ERRORLEVEL%
