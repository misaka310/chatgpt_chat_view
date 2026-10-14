@echo off
setlocal
cd /d "%~dp0"
title ChatGPT Usage Dashboard Site

call start.bat --no-open
if errorlevel 1 goto :error

".venv\Scripts\python.exe" scripts\start_sites_dashboard.py --skip-analysis %*
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Failed to prepare the ChatGPT Sites dashboard.
pause
exit /b 1
