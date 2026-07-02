@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

%PY% analyze_chat_export.py --input-dir input --output-dir output --timezone Asia/Tokyo --rebuild
if errorlevel 1 pause
%PY% analyze_gpt_3h_limit.py --input-dir input --output-dir output --timezone Asia/Tokyo --threshold 160 --window-hours 3
if errorlevel 1 pause
%PY% scripts\patch_3h_html.py --output-dir output
if errorlevel 1 pause
%PY% scripts\inject_3h_into_dashboard.py --output-dir output
if errorlevel 1 pause
%PY% scripts\patch_dashboard_daily_chart.py --output-dir output
if errorlevel 1 pause

if exist "output\index.html" del "output\index.html"
