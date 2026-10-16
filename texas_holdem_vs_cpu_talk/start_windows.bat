@echo off
cd /d "%~dp0"
py -3 run.py 2>nul || python run.py
pause
