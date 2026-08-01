@echo off
setlocal
cd /d "%~dp0.."
set "SETUP_MARKER=.venv\.dashboard-setup-complete"

if exist "%SETUP_MARKER%" del /q "%SETUP_MARKER%"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python 3.11 or newer was not found.
    echo Install Python from https://www.python.org/ and run start.bat again.
    exit /b 1
  )
  set "PY=python"
)

%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo Python 3.11 or newer is required.
  exit /b 1
)

echo Creating virtual environment...
%PY% -m venv .venv
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

> "%SETUP_MARKER%" echo ready

echo.
echo Setup complete. Starting the dashboard is handled by start.bat.
