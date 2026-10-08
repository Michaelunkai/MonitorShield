@echo off
title MonitorShield Tests
echo.
echo  ============================================
echo   MonitorShield - Running All Tests
echo  ============================================
echo.

cd /d "%~dp0src"
python -m monitor_shield --test

echo.
echo  Component tests complete.
echo.
pause
