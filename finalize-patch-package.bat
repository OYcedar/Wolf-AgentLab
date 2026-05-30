@echo off
setlocal

if "%~1"=="" (
  echo Usage: finalize-patch-package.bat PATCH_DIR [PASSWORD]
  exit /b 2
)

set "ROOT=%~dp0"
set "PATCH_DIR=%~1"
set "PASSWORD=%~2"

if "%PASSWORD%"=="" set "PASSWORD=sstm"

python "%ROOT%scripts\finalize_patch_package.py" --patch-dir "%PATCH_DIR%" --password "%PASSWORD%"
exit /b %ERRORLEVEL%
