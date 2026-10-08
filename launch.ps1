# MonitorShield - PowerShell Launcher
# Launch with isolation OFF (press Shift+S to toggle)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "   MonitorShield - Full-Monitor Isolation" -ForegroundColor Cyan
Write-Host "   One monitor. One world. No crossover." -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  Python: $pythonVersion" -ForegroundColor Gray
} catch {
    Write-Host "  ERROR: Python not found on PATH" -ForegroundColor Red
    Write-Host "  Install Python 3.8+ from https://www.python.org" -ForegroundColor Yellow
    exit 1
}

# Check dependencies
Write-Host "  Checking dependencies..." -ForegroundColor Gray
pip install pystray pillow keyboard --quiet 2>$null

# Launch
Write-Host "  Starting MonitorShield..." -ForegroundColor Green
Write-Host "  Hotkey: Shift+S (toggle) | Shift+Q (quit)" -ForegroundColor Yellow
Write-Host ""

Set-Location "$ScriptDir\src"
python -m monitor_shield @args
