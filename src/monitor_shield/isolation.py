"""
MonitorShield - Core isolation engine.

Enforces per-monitor window containment using:
  1. Window-to-monitor binding (snapshot on enable)
  2. Continuous enforcement (150ms poll + location-change hook)
  3. Cross-monitor focus-steal blocking (SetWinEventHook on EVENT_SYSTEM_FOREGROUND)
  4. Popup/owned-window redirection to parent's monitor
  5. Low-level mouse hook blocking cross-monitor clicks

All enforcement is non-destructive: no process termination, no permanent
window-style changes, no driver installation. Disabling immediately
restores normal Windows behaviour.
"""

import ctypes
import ctypes.wintypes as wintypes
import threading
import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Callable

from .display import (
    MonitorInfo,
    WindowInfo,
    enumerate_monitors,
    enumerate_windows,
    get_monitor_for_window,
    get_monitor_for_point,
    RECT,
    POINT,
    user32,
    kernel32,
)

log = logging.getLogger("MonitorShield.isolation")

# ── Win32 constants ─────────────────────────────────────────────────────────

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040

WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNTHREAD = 0x0001
WINEVENT_SKIPOWNPROCESS = 0x0002

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_LOCATIONCHANGE = 0x800B

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_QUIT = 0x0012
PM_REMOVE = 0x0001


# ── Structures ──────────────────────────────────────────────────────────────

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


# ── WinEvent callback type ─────────────────────────────────────────────────

WINEVENTPROC = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
)

HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


# ── Foreground-hook thread ─────────────────────────────────────────────────

class ForegroundHook:
    """
    Dedicated thread with a SetWinEventHook on EVENT_SYSTEM_FOREGROUND.

    Intercepts cross-monitor focus-steal attempts in real time by
    re-asserting the previous foreground window when a window on a
    different monitor tries to become foreground.
    """

    def __init__(self, engine: "IsolationEngine"):
        self._engine = engine
        self._hook_handle: int = 0
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._active = False
        self._callback_ref = None  # prevent GC
        self._last_good_fg: int = 0
        self._blocked_count: int = 0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def blocked(self) -> int:
        return self._blocked_count

    def start(self):
        if self._active:
            return
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="MS-FgHook")
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def stop(self):
        if not self._active and not self._thread:
            return
        self._stop.set()
        if self._thread_id:
            try:
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._active = False
        self._thread_id = None

    def _run(self):
        try:
            self._thread_id = kernel32.GetCurrentThreadId()

            def _cb(hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
                if idObject != 0:  # OBJID_WINDOW
                    return
                try:
                    self._on_fg(hwnd)
                except Exception:
                    pass

            self._callback_ref = WINEVENTPROC(_cb)
            self._hook_handle = user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND,
                EVENT_SYSTEM_FOREGROUND,
                0,  # system-wide, out-of-context
                self._callback_ref,
                0, 0,
                WINEVENT_OUTOFCONTEXT,
            )
        except Exception:
            self._hook_handle = 0

        if not self._hook_handle:
            self._ready.set()
            return

        self._active = True
        self._ready.set()

        msg = MSG()
        while not self._stop.is_set():
            try:
                has = user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, PM_REMOVE)
                if has:
                    if msg.message == WM_QUIT:
                        break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.01)
            except Exception:
                time.sleep(0.01)

        if self._hook_handle:
            try:
                user32.UnhookWinEvent(self._hook_handle)
            except Exception:
                pass
            self._hook_handle = 0
        self._active = False

    def _on_fg(self, hwnd: int):
        engine = self._engine
        if not engine.enabled or not hwnd:
            return

        monitors = engine._monitor_cache
        assignments = engine._window_assignments
        target_mon = get_monitor_for_window(hwnd, monitors)
        if not target_mon:
            return

        assigned = assignments.get(hwnd)
        if assigned is None:
            owner = user32.GetWindow(hwnd, 4)  # GW_OWNER
            assigned = assignments.get(owner) if owner else None

        anchor = engine._anchor_monitor

        if assigned is not None and anchor is not None and assigned != anchor:
            self._blocked_count += 1
            engine._stats["focus_steals_blocked"] = engine._stats.get("focus_steals_blocked", 0) + 1

            restore = self._last_good_fg
            if restore and restore != hwnd:
                try:
                    if user32.IsWindowVisible(restore):
                        user32.SetForegroundWindow(restore)
                except Exception:
                    pass
            log.debug(
                "Blocked cross-monitor focus: hwnd=%s monitor=(%s,%s)",
                hwnd, target_mon.left, target_mon.top,
            )
            return

        if user32.IsWindowVisible(hwnd):
            self._last_good_fg = hwnd
            engine._anchor_monitor = assigned if assigned is not None else target_mon.handle


# ── Isolation engine ───────────────────────────────────────────────────────


class IsolationEngine:
    """
    Core monitor-isolation engine.

    When enabled:
      - Snapshots all visible windows and binds each to its current monitor.
      - Continuously enforces that windows stay on their assigned monitor.
      - Blocks cross-monitor focus stealing via WinEvent hook.
      - Redirects new popup/owned windows to their parent's monitor.
      - Blocks cross-monitor mouse clicks via low-level hook.
    """

    def __init__(self):
        self._enabled = False
        self._lock = threading.Lock()
        self._window_assignments: Dict[int, int] = {}  # hwnd -> monitor_handle
        self._monitor_cache: List[MonitorInfo] = []
        self._enforcement_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._poll_interval = 0.15  # seconds

        self._stats: Dict[str, int] = {
            "windows_tracked": 0,
            "moves_blocked": 0,
            "popups_blocked": 0,
            "focus_steals_blocked": 0,
            "clicks_blocked": 0,
        }

        # Callbacks
        self._on_state_changed: Optional[Callable[[bool], None]] = None
        self._on_event: Optional[Callable[[str], None]] = None

        # Focus-blocking state
        self._anchor_monitor: Optional[int] = None
        self._hook: Optional[ForegroundHook] = None

        # Mouse hook state
        self._mouse_hook = None
        self._mouse_callback = None

    # ── Public properties ───────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    # ── Callback registration ───────────────────────────────────────────

    def on_state_changed(self, cb: Callable[[bool], None]):
        self._on_state_changed = cb

    def on_event(self, cb: Callable[[str], None]):
        self._on_event = cb

    def _fire_event(self, msg: str):
        log.info(msg)
        if self._on_event:
            try:
                self._on_event(msg)
            except Exception:
                pass

    def _fire_state(self, enabled: bool):
        if self._on_state_changed:
            try:
                self._on_state_changed(enabled)
            except Exception:
                pass

    # ── Enable / Disable / Toggle ───────────────────────────────────────

    def enable(self):
        if self._enabled:
            return
        with self._lock:
            self._monitor_cache = enumerate_monitors()
            self._capture_current_state()
            self._enabled = True
            self._stop_event.clear()

            # Determine initial anchor monitor from current foreground window
            try:
                fg = user32.GetForegroundWindow()
                if fg:
                    fg_mon = get_monitor_for_window(fg, self._monitor_cache)
                    if fg_mon:
                        self._anchor_monitor = fg_mon.handle
            except Exception:
                pass
            if self._anchor_monitor is None and self._monitor_cache:
                primary = next(
                    (m for m in self._monitor_cache if m.is_primary),
                    self._monitor_cache[0],
                )
                self._anchor_monitor = primary.handle

            # Start enforcement thread
            self._enforcement_thread = threading.Thread(
                target=self._enforcement_loop, daemon=True, name="MS-Enforce"
            )
            self._enforcement_thread.start()

            # Start foreground-steal blocking hook
            self._hook = ForegroundHook(self)
            self._hook.start()

            # Start mouse hook
            self._install_mouse_hook()

            self._fire_event(
                f"Isolation ENABLED — tracking {len(self._window_assignments)} windows "
                f"across {len(self._monitor_cache)} monitors"
            )
            self._fire_state(True)

    def disable(self):
        if not self._enabled:
            return
        with self._lock:
            self._enabled = False
            self._stop_event.set()

            if self._hook:
                try:
                    self._hook.stop()
                except Exception:
                    pass
                self._hook = None

            self._remove_mouse_hook()

            if self._enforcement_thread:
                self._enforcement_thread.join(timeout=2.0)
                self._enforcement_thread = None

            self._window_assignments.clear()
            self._anchor_monitor = None
            self._stats = {
                "windows_tracked": 0,
                "moves_blocked": 0,
                "popups_blocked": 0,
                "focus_steals_blocked": 0,
                "clicks_blocked": 0,
            }
            self._fire_event("Isolation DISABLED")
            self._fire_state(False)

    def toggle(self):
        if self._enabled:
            self.disable()
        else:
            self.enable()

    # ── Window capture ──────────────────────────────────────────────────

    def _capture_current_state(self):
        self._window_assignments.clear()
        windows = enumerate_windows(self._monitor_cache)
        for w in windows:
            self._window_assignments[w.hwnd] = w.monitor_handle
        self._stats["windows_tracked"] = len(self._window_assignments)

    # ── Enforcement loop ────────────────────────────────────────────────

    def _enforcement_loop(self):
        while not self._stop_event.is_set():
            try:
                self._enforce()
            except Exception as e:
                log.debug("Enforcement error: %s", e)
            self._stop_event.wait(self._poll_interval)

    def _enforce(self):
        with self._lock:
            if not self._enabled:
                return

            # Refresh monitors (detect connect/disconnect)
            new_mons = enumerate_monitors()
            if new_mons:
                self._monitor_cache = new_mons

            current = enumerate_windows(self._monitor_cache)
            current_hwnds = {w.hwnd for w in current}

            # Remove stale windows
            stale = [h for h in self._window_assignments if h not in current_hwnds]
            for h in stale:
                del self._window_assignments[h]

            for w in current:
                # New window → assign to owner's monitor or current monitor
                if w.hwnd not in self._window_assignments:
                    if w.owner_hwnd and w.owner_hwnd in self._window_assignments:
                        owner_mon = self._window_assignments[w.owner_hwnd]
                        self._window_assignments[w.hwnd] = owner_mon
                        self._assign_to_monitor(w, owner_mon)
                        self._stats["popups_blocked"] += 1
                    else:
                        self._window_assignments[w.hwnd] = w.monitor_handle

                assigned_mon = self._window_assignments.get(w.hwnd)
                if assigned_mon and w.monitor_handle != assigned_mon:
                    if not w.is_minimized and not w.is_maximized:
                        self._snap_back(w, assigned_mon)
                        self._stats["moves_blocked"] += 1
                elif assigned_mon and not w.is_minimized:
                    mon = self._mon_by_handle(assigned_mon)
                    if mon and not mon.contains_rect(*w.rect):
                        if not w.is_maximized:
                            self._snap_back(w, assigned_mon)
                            self._stats["moves_blocked"] += 1

            self._stats["windows_tracked"] = len(self._window_assignments)

    # ── Mouse hook ──────────────────────────────────────────────────────

    def _install_mouse_hook(self):
        if self._mouse_hook:
            return

        def _cb(n_code, w_param, l_param):
            if not self._enabled or n_code < 0:
                return user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)
            try:
                hs = MSLLHOOKSTRUCT.from_address(l_param)
                cx, cy = hs.pt.x, hs.pt.y
                cursor_mon = None
                for m in self._monitor_cache:
                    if m.contains_point(cx, cy):
                        cursor_mon = m
                        break
                if not cursor_mon:
                    return user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)

                fg = user32.GetForegroundWindow()
                if not fg:
                    return user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)

                fg_mon = get_monitor_for_window(fg, self._monitor_cache)
                if not fg_mon:
                    return user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)

                if cursor_mon.handle != fg_mon.handle and w_param in (
                    WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN
                ):
                    self._stats["clicks_blocked"] = self._stats.get("clicks_blocked", 0) + 1
                    return 1  # Block the click
            except Exception:
                pass
            return user32.CallNextHookEx(self._mouse_hook, n_code, w_param, l_param)

        self._mouse_callback = HOOKPROC(_cb)
        h_mod = kernel32.GetModuleHandleW(None)
        if h_mod:
            self._mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_callback, h_mod, 0)
        if not self._mouse_hook:
            try:
                h_user32 = kernel32.GetModuleHandleW("user32.dll")
                if h_user32:
                    self._mouse_hook = user32.SetWindowsHookExW(
                        WH_MOUSE_LL, self._mouse_callback, h_user32, 0
                    )
            except Exception:
                pass
        if self._mouse_hook:
            log.info("Mouse hook installed — cross-monitor click blocking active")
        else:
            log.warning("Mouse hook unavailable; isolation via window confinement + focus hooks")

    def _remove_mouse_hook(self):
        if self._mouse_hook:
            try:
                user32.UnhookWindowsHookEx(self._mouse_hook)
            except Exception:
                pass
            self._mouse_hook = None

    # ── Window helpers ──────────────────────────────────────────────────

    def _mon_by_handle(self, handle: int) -> Optional[MonitorInfo]:
        for m in self._monitor_cache:
            if m.handle == handle:
                return m
        return None

    def _assign_to_monitor(self, w: WindowInfo, monitor_handle: int):
        mon = self._mon_by_handle(monitor_handle)
        if not mon:
            return
        win_w = min(w.rect[2] - w.rect[0], mon.width)
        win_h = min(w.rect[3] - w.rect[1], mon.height)
        new_x = mon.left + (mon.width - win_w) // 2
        new_y = mon.top + (mon.height - win_h) // 4
        try:
            user32.SetWindowPos(
                w.hwnd, 0, new_x, new_y, win_w, win_h,
                SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            pass

    def _snap_back(self, w: WindowInfo, target_handle: int):
        mon = self._mon_by_handle(target_handle)
        if not mon:
            return
        win_w = min(w.rect[2] - w.rect[0], mon.width)
        win_h = min(w.rect[3] - w.rect[1], mon.height)
        new_x = mon.left + (mon.width - win_w) // 2
        new_y = mon.top + (mon.height - win_h) // 4
        new_y = max(new_y, mon.work_top)
        new_y = min(new_y, mon.work_bottom - win_h)
        try:
            user32.SetWindowPos(
                w.hwnd, 0, new_x, new_y, win_w, win_h,
                SWP_NOZORDER | SWP_NOACTIVATE,
            )
            log.debug("Snapped '%s' back to (%s,%s)", w.title[:30], mon.left, mon.top)
        except Exception:
            pass

    # ── Status queries ──────────────────────────────────────────────────

    def get_status_summary(self) -> str:
        if not self._enabled:
            return "Isolation: OFF"
        s = self._stats
        n_mon = len(self._monitor_cache)
        hook_state = "on" if (self._hook and self._hook.active) else "off"
        return (
            f"Isolation: ON | {s['windows_tracked']} windows tracked | "
            f"{s['moves_blocked']} moves blocked | {s['popups_blocked']} popups redirected | "
            f"{s.get('focus_steals_blocked', 0)} focus steals blocked (hook {hook_state}) | "
            f"{s.get('clicks_blocked', 0)} clicks blocked | {n_mon} monitor(s)"
        )

    def get_monitor_info_text(self) -> str:
        self._monitor_cache = enumerate_monitors()
        lines = []
        for i, m in enumerate(self._monitor_cache):
            tag = " [PRIMARY]" if m.is_primary else ""
            lines.append(f"  Monitor {i}: {m.width}x{m.height} at ({m.left},{m.top}){tag}")
        return "\n".join(lines)
