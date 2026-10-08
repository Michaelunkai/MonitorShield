"""
MonitorShield - Core display and monitor utilities.

Provides monitor enumeration, window enumeration, and monitor-info dataclasses
using raw Win32 APIs (no external dependencies beyond ctypes).
"""

import ctypes
import ctypes.wintypes as wintypes
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ── Win32 constants ─────────────────────────────────────────────────────────

MONITOR_DEFAULTTONEAREST = 2
MONITOR_DEFAULTTOPRIMARY = 1

GW_OWNER = 4
GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_VISIBLE = 0x10000000
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_MINIMIZE = 0x20000000
WS_MAXIMIZE = 0x01000000

WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# ── Win32 handles ───────────────────────────────────────────────────────────

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

# ── Structures ──────────────────────────────────────────────────────────────


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class MonitorInfo:
    """Immutable description of a connected display."""
    handle: int
    left: int
    top: int
    right: int
    bottom: int
    work_left: int
    work_top: int
    work_right: int
    work_bottom: int
    is_primary: bool
    name: str = ""

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def contains_point(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom

    def contains_rect(self, left: int, top: int, right: int, bottom: int) -> bool:
        return (
            left >= self.left
            and top >= self.top
            and right <= self.right
            and bottom <= self.bottom
        )

    def center(self) -> Tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def clamp_rect(
        self, left: int, top: int, width: int, height: int
    ) -> Tuple[int, int, int, int]:
        """Clamp a rect so it fits entirely within this monitor. Returns (x, y, w, h)."""
        w = min(width, self.width)
        h = min(height, self.height)
        x = max(self.left, min(left, self.right - w))
        y = max(self.top, min(top, self.bottom - h))
        return x, y, w, h


@dataclass
class WindowInfo:
    """Properties of a single visible top-level window."""
    hwnd: int
    title: str
    process_name: str
    monitor_handle: int
    rect: Tuple[int, int, int, int]  # left, top, right, bottom
    style: int
    ex_style: int
    owner_hwnd: int
    is_visible: bool
    is_tool_window: bool
    is_popup: bool
    is_minimized: bool
    is_maximized: bool


# ── Monitor enumeration ─────────────────────────────────────────────────────


def enumerate_monitors() -> List[MonitorInfo]:
    """Return all connected monitors with their bounds."""
    monitors: List[MonitorInfo] = []

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HDC,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def _cb(hMonitor, hdcMonitor, lprcMonitor, dwData):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi)):
            name = f"Monitor-{len(monitors)}"
            try:
                buf = ctypes.create_unicode_buffer(256)
            except Exception:
                pass
            monitors.append(
                MonitorInfo(
                    handle=hMonitor,
                    left=mi.rcMonitor.left,
                    top=mi.rcMonitor.top,
                    right=mi.rcMonitor.right,
                    bottom=mi.rcMonitor.bottom,
                    work_left=mi.rcWork.left,
                    work_top=mi.rcWork.top,
                    work_right=mi.rcWork.right,
                    work_bottom=mi.rcWork.bottom,
                    is_primary=bool(mi.dwFlags & 1),
                    name=name,
                )
            )
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
    return monitors


def get_monitor_for_window(hwnd: int, monitors: List[MonitorInfo]) -> Optional[MonitorInfo]:
    """Find which monitor a window is on."""
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    for m in monitors:
        if m.handle == hmon:
            return m
    return monitors[0] if monitors else None


def get_monitor_for_point(
    x: int, y: int, monitors: List[MonitorInfo]
) -> Optional[MonitorInfo]:
    """Find which monitor contains a screen point."""
    pt = POINT(x, y)
    hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
    for m in monitors:
        if m.handle == hmon:
            return m
    return monitors[0] if monitors else None


# ── Window enumeration ──────────────────────────────────────────────────────


def _get_window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_process_name(hwnd: int) -> str:
    try:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return ""
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return ""
        buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(size)):
            kernel32.CloseHandle(hproc)
            return buf.value.split("\\")[-1]
        kernel32.CloseHandle(hproc)
    except Exception:
        pass
    return ""


def _is_cloaked(hwnd: int) -> bool:
    """Check if a window is cloaked (UWP hidden windows)."""
    DWMWA_CLOAKED = 14
    cloaked = wintypes.DWORD()
    try:
        dwmapi.DwmGetWindowAttribute(
            hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        return cloaked.value != 0
    except Exception:
        return False


def enumerate_windows(monitors: List[MonitorInfo]) -> List[WindowInfo]:
    """Enumerate all visible top-level windows and their properties."""
    windows: List[WindowInfo] = []

    ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, lParam):
        if not hwnd:
            return True

        style = user32.GetWindowLongW(hwnd, GWL_STYLE)

        # Skip invisible windows
        if not (user32.IsWindowVisible(hwnd) or (style & WS_VISIBLE)):
            return True

        # Skip cloaked UWP windows
        if _is_cloaked(hwnd):
            return True

        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

        # Skip child windows
        if style & WS_CHILD:
            return True

        # Get window rect
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))

        # Get monitor
        mon = get_monitor_for_window(hwnd, monitors)
        if not mon:
            return True

        owner = user32.GetWindow(hwnd, GW_OWNER)
        title = _get_window_text(hwnd)
        proc = _get_process_name(hwnd)

        windows.append(
            WindowInfo(
                hwnd=hwnd,
                title=title,
                process_name=proc,
                monitor_handle=mon.handle,
                rect=(rect.left, rect.top, rect.right, rect.bottom),
                style=style,
                ex_style=ex_style,
                owner_hwnd=owner,
                is_visible=True,
                is_tool_window=bool(ex_style & WS_EX_TOOLWINDOW),
                is_popup=bool(style & WS_POPUP) and not bool(style & WS_CHILD),
                is_minimized=bool(style & WS_MINIMIZE),
                is_maximized=bool(style & WS_MAXIMIZE),
            )
        )
        return True

    user32.EnumWindows(ENUMPROC(_cb), 0)
    return windows
