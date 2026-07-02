@echo off
if exist "output\dashboard.html" py -3 scripts\patch_dashboard_daily_chart.py --output-dir output
py -3 scripts\open_dashboard.py --output-dir output --page dashboard.html
