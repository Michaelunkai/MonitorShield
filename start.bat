@echo off
title MonitorShield
echo.
echo  ============================================
echo   MonitorShield - Full-Monitor Isolation
echo   One monitor. One world. No crossover.
echo  ============================================
echo.
echo  Starting MonitorShield...
echo  Press Shift+S to toggle isolation
echo  Press Shift+Q to quit
echo.

cd /d "%~dp0src"
python -m monitor_shield %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo  [ERROR] MonitorShield exited with code %ERRORLEVEL%
    echo  Make sure Python 3.8+ is installed and on PATH.
    echo.
    pause
)
