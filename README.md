# MonitorShield 🛡️

**Full-monitor isolation for Windows.** One monitor, one world, no crossover.

## What It Does

When **enabled**, MonitorShield:

- **Pins windows to their monitors** — a window moved from its assigned monitor snaps back instantly
- **Blocks cross-monitor focus stealing** — a `SetWinEventHook` on `EVENT_SYSTEM_FOREGROUND` intercepts focus theft in real time
- **Blocks cross-monitor mouse clicks** — a low-level mouse hook prevents clicking on a different monitor from stealing focus
- **Redirects popups** — new popup/owned windows are forced onto the same monitor as their parent
- **Enforces full containment** — window rects that straddle a monitor boundary are snapped back inside
- **Shows a beautiful shield icon** in the system tray (green = ON, amber = OFF, red = conflict)

## Use Cases

| Scenario | What MonitorShield Protects |
|---|---|
| **Gaming + AI Agents** | Game on Monitor 1 stays untouched while agents run on Monitor 2+ |
| **Secure Workstation** | Sensitive apps isolated from general browsing and communication |
| **Presentation Mode** | Notes/chat never flash onto the presentation display |
| **Development + Monitoring** | Build/test on one screen, dashboards on another — zero overlap |

## Quick Start

### Option 1: Double-click `start.bat`
Launches with isolation OFF. Press **Shift+S** to toggle.

### Option 2: Double-click `start_isolated.bat`
Launches with isolation ON immediately.

### Option 3: PowerShell
```powershell
.\launch.ps1
```

### Option 4: Silent (no console window)
Double-click `MonitorShield-Silent.vbs`

### Option 5: Command line
```bash
cd src
python -m monitor_shield                # Start with isolation OFF
python -m monitor_shield --start-on     # Start with isolation ON
python -m monitor_shield --test         # Run component tests
python -m monitor_shield --info         # Show monitor + window info
```

## Hotkeys

| Key | Action |
|-----|--------|
| **Shift+S** | Toggle isolation ON/OFF |
| **Shift+Q** | Quit MonitorShield |

## System Tray

Right-click the shield icon for:
- **Enable/Disable Isolation** — toggle on/off
- **Show Status** — window count, moves blocked, focus steals blocked
- **Show Monitors** — list connected monitors
- **Quit** — exit the application

### Icon States

| Colour | Meaning |
|--------|---------|
| 🟢 Green shield | Isolation ACTIVE — all displays sealed |
| 🟡 Amber shield | Standby — isolation OFF |
| 🔴 Red shield | Conflict detected — cross-monitor event was blocked |

## How It Works

1. **Window Tracking**: On enable, snapshots all visible windows and records which monitor each is on.
2. **Continuous Enforcement**: Every 150ms, checks if any window moved to a different monitor — or straddles a boundary — and snaps it back.
3. **Focus-Steal Blocking**: A dedicated thread installs a `SetWinEventHook` on `EVENT_SYSTEM_FOREGROUND`. When a window on monitor B tries to become foreground while focus belongs to monitor A, the hook re-asserts the previous foreground window.
4. **Mouse-Click Blocking**: A low-level mouse hook (`SetWindowsHookEx`) blocks cross-monitor mouse clicks that would otherwise steal focus.
5. **Popup Redirection**: New popup/owned windows are assigned to their owner's monitor and centered there.
6. **Clean Disable**: When turned off, all hooks are removed, all tracking is released, and windows move freely again.

## Architecture

```
MonitorShield/
├── start.bat                    # Quick launcher
├── start_isolated.bat           # Launch with isolation ON
├── launch.ps1                   # PowerShell launcher (auto-installs deps)
├── MonitorShield-Silent.vbs     # Silent launcher (no console)
├── run_tests.bat                # Run ALL test suites
├── info.bat                     # Show monitor info
├── requirements.txt             # Python dependencies
├── README.md                    # This file
├── src/
│   └── monitor_shield/
│       ├── __init__.py          # Package metadata
│       ├── __main__.py          # Entry point + CLI + tray app + single-instance
│       ├── display.py           # Monitor + window enumeration (Win32 API)
│       ├── isolation.py         # Core isolation engine + ForegroundHook + mouse hook
│       ├── icon.py              # Dynamic tray icon renderer (Pillow)
│       ├── hotkey.py            # Shift+S / Shift+Q global hotkey (keyboard lib + Win32 fallback)
│       ├── tray.py              # System tray icon manager (pystray)
│       ├── logs/                # Runtime logs
│       └── data/                # Runtime data
├── tests/
│   ├── full_test_suite.py       # 40+ comprehensive tests
│   └── integration_test.py      # 12+ integration tests
└── docs/
    └── architecture.md          # Technical deep-dive
```

## Tests

| Suite | Count | Run |
|-------|-------|-----|
| Component | 6 | `python -m monitor_shield --test` |
| Full suite | 40+ | `python tests\full_test_suite.py` |
| Integration | 12+ | `python tests\integration_test.py` |
| **All** | **58+** | **`run_tests.bat`** |

## Requirements

| Requirement | Detail |
|---|---|
| **OS** | Windows 10 (1809+) or Windows 11 |
| **Displays** | 2+ connected monitors (works with 1, for testing) |
| **Runtime** | Python 3.8+ |
| **Privileges** | Standard user — no admin elevation required |
| **Dependencies** | `pystray`, `Pillow`, `keyboard` (auto-installed by launch script) |

## Location

```
F:\study\Systems\Windows\Desktop\WindowManagement\MonitorIsolation\MonitorShield
```
(6 layers deep under `F:\study`)

## Why This Location?

Placed under `WindowManagement` because MonitorShield is fundamentally a **window management tool** — it manages how windows interact across display boundaries. The path hierarchy is:

- **Systems** → **Windows** → **Desktop** → **WindowManagement** → **MonitorIsolation** → **MonitorShield**

## Notes

- The tool does NOT kill, modify, or inject into any process — it only moves windows back to their assigned monitor and re-asserts focus on cross-monitor steal attempts
- Works with any number of monitors (1, 2, 3, ...)
- Single-instance enforcement prevents duplicate launches
- Logs are saved to `src/logs/`
- Admin privileges recommended for full isolation capabilities (some Win32 operations require elevation)
- The `keyboard` library is used for hotkey registration with automatic Win32 `RegisterHotKey` fallback
- No port, pipe, or named resource conflicts with other applications

## License

MIT — use it, modify it, ship it.
