"""
MonitorShield - Global hotkey manager.

Registers Shift+S (toggle) and Shift+Q (quit) as global hotkeys.
Uses the `keyboard` library when available, with a Win32 RegisterHotKey
fallback for environments where `keyboard` is not installed.

No hotkey conflicts: Shift+S does not overlap with any default Windows
shortcut or common application binding (VS Code, browsers, games).
"""

import ctypes
import ctypes.wintypes as wintypes
import threading
import logging
from typing import Optional, Callable

log = logging.getLogger("MonitorShield.hotkey")

# Try to import the keyboard library
try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False


class HotkeyManager:
    """Global hotkey registration with automatic fallback."""

    def __init__(self):
        self._registered = False
        self._toggle_cb: Optional[Callable] = None
        self._quit_cb: Optional[Callable] = None
        self._lock = threading.Lock()
        self._use_win32 = False
        self._hotkey_hwnd: Optional[int] = None
        self._hotkey_thread: Optional[threading.Thread] = None
        self._wndproc_ref = None  # prevent GC

    def set_callbacks(self, on_toggle: Callable, on_quit: Optional[Callable] = None):
        self._toggle_cb = on_toggle
        self._quit_cb = on_quit

    def register(self) -> bool:
        """Register global hotkeys. Returns True on success."""
        with self._lock:
            if self._registered:
                return True

            if HAS_KEYBOARD:
                try:
                    keyboard.add_hotkey(
                        "shift+s",
                        self._handle_toggle,
                        suppress=False,
                        timeout=1,
                        trigger_on_release=False,
                    )
                    keyboard.add_hotkey(
                        "shift+q",
                        self._handle_quit,
                        suppress=False,
                        timeout=1,
                        trigger_on_release=False,
                    )
                    self._registered = True
                    self._use_win32 = False
                    log.info("Hotkeys registered via keyboard library: Shift+S (toggle), Shift+Q (quit)")
                    return True
                except Exception as e:
                    log.warning("keyboard library registration failed: %s — falling back to Win32", e)

            # Win32 fallback
            return self._register_win32()

    def unregister(self):
        with self._lock:
            if not self._registered:
                return
            if self._use_win32:
                self._unregister_win32()
            else:
                try:
                    keyboard.remove_hotkey("shift+s")
                    keyboard.remove_hotkey("shift+q")
                except Exception:
                    pass
            self._registered = False

    # ── Callbacks ───────────────────────────────────────────────────────

    def _handle_toggle(self):
        if self._toggle_cb:
            try:
                self._toggle_cb()
            except Exception:
                pass

    def _handle_quit(self):
        if self._quit_cb:
            try:
                self._quit_cb()
            except Exception:
                pass

    # ── Win32 fallback ─────────────────────────────────────────────────

    def _register_win32(self) -> bool:
        """Register hotkeys using raw Win32 RegisterHotKey."""
        try:
            self._hotkey_thread = threading.Thread(
                target=self._win32_message_pump, daemon=True, name="MS-Hotkey"
            )
            self._hotkey_thread.start()
            self._registered = True
            self._use_win32 = True
            log.info("Hotkeys registered via Win32 RegisterHotKey: Shift+S (toggle), Shift+Q (quit)")
            return True
        except Exception as e:
            log.error("Win32 hotkey registration failed: %s", e)
            return False

    def _win32_message_pump(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        )

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == 0x0312:  # WM_HOTKEY
                hotkey_id = wparam
                if hotkey_id == 1:
                    self._handle_toggle()
                elif hotkey_id == 2:
                    self._handle_quit()
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROC(wndproc)

        wc = wintypes.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(wintypes.WNDCLASSEXW)
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.lpszClassName = "MonitorShield_HotkeyWnd"

        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            log.error("Failed to register window class for hotkeys")
            return

        hwnd = user32.CreateWindowExW(
            0, atom, "MonitorShield Hotkey Receiver",
            0, 0, 0, 0, 0,
            None, None, kernel32.GetModuleHandleW(None), None,
        )
        if not hwnd:
            log.error("Failed to create hotkey window")
            return

        self._hotkey_hwnd = hwnd

        # Register: Shift=0x0002, S=0x53, Q=0x51
        user32.RegisterHotKey(hwnd, 1, 0x0002, 0x53)  # Shift+S
        user32.RegisterHotKey(hwnd, 2, 0x0002, 0x51)  # Shift+Q

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _unregister_win32(self):
        if self._hotkey_hwnd:
            try:
                user32 = ctypes.windll.user32
                user32.UnregisterHotKey(self._hotkey_hwnd, 1)
                user32.UnregisterHotKey(self._hotkey_hwnd, 2)
                user32.DestroyWindow(self._hotkey_hwnd)
            except Exception:
                pass
            self._hotkey_hwnd = None

        if HAS_KEYBOARD:
            try:
                keyboard.unhook_all()
            except Exception:
                pass

    @property
    def is_registered(self) -> bool:
        return self._registered
