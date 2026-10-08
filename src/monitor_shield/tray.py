"""
MonitorShield - System tray icon manager.

Manages a beautiful shield icon in the Windows system tray with:
  - Dynamic state coloring (green/amber/red)
  - Context menu with status, monitor info, toggle, and quit
  - Tooltip showing current state and hotkey hint
"""

import os
import threading
from typing import Optional, Callable

try:
    import pystray
    from pystray import MenuItem, Menu
    from PIL import Image
except ImportError:
    pystray = None

from .icon import generate_icon


class TrayIcon:
    """System tray icon for MonitorShield."""

    def __init__(self):
        self._icon: Optional[pystray.Icon] = None if pystray else None
        self._enabled = False
        self._conflict = False
        self._running = False
        self._lock = threading.Lock()
        self._frame = 0

        # Callbacks
        self.on_toggle: Optional[Callable] = None
        self.on_quit: Optional[Callable] = None
        self.on_show_status: Optional[Callable] = None

    def _make_icon(self) -> "Image.Image":
        """Generate the current-state icon image."""
        return generate_icon(
            size=64,
            active=self._enabled,
            conflict=self._conflict,
            frame=self._frame,
        )

    def _tooltip(self) -> str:
        state = "ON" if self._enabled else "OFF"
        return f"MonitorShield [{state}] — Shift+S to toggle"

    def _build_menu(self):
        if not pystray:
            return None
        status_text = "ISOLATION ACTIVE" if self._enabled else "Standby"
        toggle_text = (
            "Disable Isolation (Shift+S)" if self._enabled
            else "Enable Isolation (Shift+S)"
        )
        return Menu(
            MenuItem(status_text, None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(toggle_text, self._on_toggle),
            MenuItem("Show Status", self._on_status),
            MenuItem("Show Monitors", self._on_monitors),
            Menu.SEPARATOR,
            MenuItem("Quit (Shift+Q)", self._on_quit),
        )

    # ── Menu callbacks ──────────────────────────────────────────────────

    def _on_toggle(self, icon=None, item=None):
        if self.on_toggle:
            self.on_toggle()

    def _on_status(self, icon=None, item=None):
        if self.on_show_status:
            self.on_show_status()

    def _on_monitors(self, icon=None, item=None):
        if self.on_show_status:
            self.on_show_status(detail="monitors")

    def _on_quit(self, icon=None, item=None):
        if self.on_quit:
            self.on_quit()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def create(self):
        """Create the tray icon (but don't start the loop yet)."""
        if not pystray:
            return
        with self._lock:
            self._icon = pystray.Icon(
                name="MonitorShield",
                icon=self._make_icon(),
                title=self._tooltip(),
                menu=self._build_menu(),
            )

    def update_state(self, enabled: bool, stats: dict = None):
        """Update the icon appearance to reflect new state."""
        with self._lock:
            self._enabled = enabled
            self._conflict = False
            if self._icon:
                try:
                    self._icon.icon = self._make_icon()
                    self._icon.title = self._tooltip()
                    self._icon.menu = self._build_menu()
                except Exception:
                    pass

    def flash_conflict(self):
        """Briefly flash the red conflict icon."""
        with self._lock:
            self._conflict = True
            if self._icon:
                try:
                    self._icon.icon = self._make_icon()
                except Exception:
                    pass

        def _reset():
            import time
            time.sleep(0.8)
            with self._lock:
                self._conflict = False
                if self._icon:
                    try:
                        self._icon.icon = self._make_icon()
                    except Exception:
                        pass

        threading.Thread(target=_reset, daemon=True).start()

    def start(self):
        """Start the tray icon (blocking — run in a thread)."""
        if not self._icon:
            self.create()
        if not self._icon:
            return
        self._running = True
        try:
            self._icon.run()
        except Exception:
            self._running = False

    def stop(self):
        """Stop the tray icon."""
        self._running = False
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._running
