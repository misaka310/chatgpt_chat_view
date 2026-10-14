@echo off
setlocal
cd /d "%~dp0"
title ChatGPT Export Usage Dashboard

set "PY=.venv\Scripts\python.exe"
set "SETUP_MARKER=.venv\.dashboard-setup-complete"

if not exist "%PY%" goto :setup
if not exist "%SETUP_MARKER%" goto :setup
"%PY%" scripts\check_environment.py >nul 2>nul
if errorlevel 1 goto :setup
goto :run

:setup
echo Preparing the local environment...
call scripts\setup.bat
if errorlevel 1 goto :error

:run
"%PY%" scripts\start_dashboard.py %*
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Failed to start the ChatGPT usage dashboard.
pause
exit /b 1
