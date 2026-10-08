@echo off
title MonitorShield (Isolation ON)
echo.
echo  ============================================
echo   MonitorShield - Starting with isolation ON
echo  ============================================
echo.

cd /d "%~dp0src"
python -m monitor_shield --start-on %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo  [ERROR] MonitorShield exited with code %ERRORLEVEL%
    pause
)
