@echo off
cd /d "%~dp0"
python -B main.py %*
if errorlevel 1 pause
