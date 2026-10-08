# MonitorShield — Architecture

## Overview

MonitorShield creates complete isolation boundaries between every connected display on a Windows system. It operates at the **window management layer** using documented Win32 APIs — no drivers, no services, no shell extensions.

## Core Components

### 1. Display Manager (`display.py`)

- Enumerates all connected monitors via `EnumDisplayMonitors` / `GetMonitorInfoW`
- Enumerates all visible top-level windows via `EnumWindows`
- Determines which monitor each window belongs to via `MonitorFromWindow`
- Handles UWP cloaked windows, child windows, and tool windows
- Pure ctypes — no external dependencies

### 2. Isolation Engine (`isolation.py`)

The heart of MonitorShield. Three enforcement layers:

#### Layer 1: Window-to-Monitor Binding
On enable, snapshots all visible windows and assigns each to its current monitor. Stores the assignment as `hwnd → monitor_handle`.

#### Layer 2: Continuous Enforcement (150ms poll)
Every 150ms, enumerates all windows again and:
- Removes stale entries (closed windows)
- Assigns new windows (popups → owner's monitor)
- Snap-backs windows that moved to a different monitor
- Snap-backs windows that straddle a monitor boundary

#### Layer 3: Real-Time Hooks
Three Win32 hooks provide sub-polling-tick response:

| Hook | Purpose |
|------|---------|
| `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` | Blocks cross-monitor focus stealing by re-asserting the previous foreground window |
| `SetWindowsHookEx(WH_MOUSE_LL)` | Blocks cross-monitor mouse clicks that would steal focus |
| `SetWinEventHook(EVENT_OBJECT_LOCATIONCHANGE)` | Detects window moves in real time for immediate snap-back |

All hooks run on dedicated threads with message pumps (required for out-of-context WinEvent delivery).

### 3. Icon Renderer (`icon.py`)

Generates a beautiful shield icon programmatically using Pillow:
- Rendered at 2× resolution for anti-aliasing, downsampled with LANCZOS
- Three states: green (active), amber (standby), red (conflict)
- Subtle pulse animation on frame changes
- Glow effect, inner highlight, status mark (checkmark / X / exclamation)
- Status dot in top-right corner
- No external icon files needed

### 4. Hotkey Manager (`hotkey.py`)

Registers Shift+S (toggle) and Shift+Q (quit):
- Primary: `keyboard` library (hooks into Windows low-level keyboard events)
- Fallback: Win32 `RegisterHotKey` with hidden message window
- Automatic fallback if `keyboard` library is unavailable
- No conflicts with default Windows shortcuts or common app bindings

### 5. Tray Icon Manager (`tray.py`)

Uses `pystray` to manage the system tray icon:
- Dynamic icon updates on state change
- Context menu with status, toggle, monitors, quit
- Desktop notifications on state change
- Tooltip shows current state and hotkey hint

### 6. Application (`__main__.py`)

Orchestrates all components:
- Single-instance enforcement via named mutex
- CLI modes: `--test`, `--info`, `--start-on`
- Logging to file + console
- Graceful cleanup on exit (unhooks, releases tracking)

## Data Flow

```
User presses Shift+S
       │
       ▼
HotkeyManager._handle_toggle()
       │
       ▼
IsolationEngine.toggle()
       │
       ├──→ enable(): snapshot windows, start enforcement thread, install hooks
       │
       └──→ disable(): stop threads, remove hooks, clear tracking
              │
              ▼
       TrayIcon.update_state() ←──── IsolationEngine._on_state_changed callback
              │
              ▼
       pystray.Icon updates icon image + tooltip + menu
```

## Thread Model

| Thread | Purpose | Lifetime |
|--------|---------|----------|
| Main | CLI parsing, app lifecycle | Entire run |
| TrayIcon | pystray message loop (blocking) | Entire run |
| MS-Enforce | 150ms polling enforcement loop | While isolation ON |
| MS-FgHook | WinEvent hook message pump | While isolation ON |
| MS-Hotkey | Win32 RegisterHotKey message pump | Entire run (if keyboard lib unavailable) |

## Non-Destructive Design

MonitorShield never:
- Kills processes
- Modifies window styles permanently
- Changes system settings
- Installs drivers or services
- Binds to ports, pipes, or named resources
- Injects into processes

Disabling immediately removes all hooks and restores normal Windows behaviour.
