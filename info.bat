@echo off
title MonitorShield Info
cd /d "%~dp0src"
python -m monitor_shield --info
pause
