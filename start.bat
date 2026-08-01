@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo First-time setup...
  call scripts\setup.bat
  if errorlevel 1 goto :error
)

"%PY%" scripts\start_dashboard.py
if errorlevel 1 goto :error
exit /b 0

:error
echo.
echo Failed to start the ChatGPT usage dashboard.
pause
exit /b 1
