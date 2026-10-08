"""
MonitorShield - System Tray Application
Full-monitor isolation for Windows. One monitor, one world, no crossover.

Entry point: creates tray icon, registers global hotkey, and runs the
isolation engine. Supports single-instance enforcement, CLI modes, and
graceful cleanup.
"""

import sys
import os
import ctypes
import logging
import threading
import time
import argparse

# Ensure the src directory is on the path for package imports
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from monitor_shield.isolation import IsolationEngine
from monitor_shield.tray import TrayIcon
from monitor_shield.hotkey import HotkeyManager
from monitor_shield.display import enumerate_monitors, enumerate_windows

try:
    import pystray
except ImportError:
    pystray = None

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="[MonitorShield] %(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("MonitorShield")


# ── Single-instance mutex ───────────────────────────────────────────────────

MUTEX_NAME = "Global\\MonitorShield_SingleInstance_{A7F2E1B3-9C4D-4E8F-B2A1-D6F3C5E8A7B0}"


def ensure_single_instance():
    """Return the mutex handle if this is the only instance; None otherwise."""
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
    error = ctypes.windll.kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    if error == ERROR_ALREADY_EXISTS:
        log.warning("Another MonitorShield instance is already running. Exiting.")
        return None
    return mutex


# ── Application ─────────────────────────────────────────────────────────────


class MonitorShieldApp:
    """Main application: tray icon, hotkeys, isolation engine."""

    def __init__(self, start_enabled: bool = False):
        self._start_enabled = start_enabled
        self._isolation = IsolationEngine()
        self._tray = TrayIcon()
        self._hotkeys = HotkeyManager()
        self._running = False

        # Wire events
        self._isolation.on_state_changed(self._on_state_changed)
        self._isolation.on_event(self._on_event)
        self._tray.on_toggle = self._toggle_isolation
        self._tray.on_quit = self._quit
        self._tray.on_show_status = self._show_status
        self._hotkeys.set_callbacks(
            on_toggle=self._toggle_isolation,
            on_quit=self._quit,
        )

    def _on_state_changed(self, enabled: bool):
        status = "ENABLED" if enabled else "DISABLED"
        log.info("Isolation %s", status)
        self._tray.update_state(enabled, self._isolation.stats)
        # Show desktop notification
        if pystray and self._tray._icon:
            try:
                msg = (
                    "Monitor isolation ENABLED — all displays are sealed."
                    if enabled
                    else "Monitor isolation DISABLED — normal behaviour restored."
                )
                self._tray._icon.notify(msg, title="MonitorShield")
            except Exception:
                pass

    def _on_event(self, msg: str):
        log.info("Engine: %s", msg)

    def _toggle_isolation(self):
        self._isolation.toggle()

    def _show_status(self, detail: str = None):
        if detail == "monitors":
            info = self._isolation.get_monitor_info_text()
            log.info("Monitor info:\n%s", info)
        else:
            status = self._isolation.get_status_summary()
            log.info(status)

    def _quit(self):
        log.info("Quitting MonitorShield...")
        self._running = False
        self._isolation.disable()
        self._hotkeys.unregister()
        self._tray.stop()

    def run(self):
        """Start the application (blocking)."""
        self._running = True

        # Banner
        print("=" * 60)
        print("  MonitorShield v1.0.0")
        print("  Full-monitor isolation for Windows")
        print("  Hotkey: Shift+S to toggle | Shift+Q to quit")
        print("=" * 60)

        # Show monitor info
        monitors = enumerate_monitors()
        log.info("Detected %d monitor(s):", len(monitors))
        for i, m in enumerate(monitors):
            tag = " [PRIMARY]" if m.is_primary else ""
            log.info("  Monitor %d: %dx%d at (%d,%d)%s", i, m.width, m.height, m.left, m.top, tag)

        # Register hotkeys
        if self._hotkeys.register():
            log.info("Hotkeys registered successfully")
        else:
            log.warning("Failed to register hotkeys — tray menu still works")

        # Start isolation if requested
        if self._start_enabled:
            self._isolation.enable()

        # Create and start tray icon
        self._tray.create()
        tray_thread = threading.Thread(target=self._tray.start, daemon=True, name="MS-Tray")
        tray_thread.start()

        time.sleep(0.5)
        log.info("MonitorShield is running. Press Shift+S to toggle isolation.")
        log.info("Right-click the tray icon for options.")

        # Keep main thread alive
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self._quit()


# ── CLI modes ───────────────────────────────────────────────────────────────


def test_mode():
    """Run component tests without starting the full app."""
    print("=" * 60)
    print("  MonitorShield — Component Test")
    print("=" * 60)

    # Test 1: Monitor enumeration
    print("\n[1] Testing monitor enumeration...")
    monitors = enumerate_monitors()
    print(f"    Found {len(monitors)} monitor(s):")
    for i, m in enumerate(monitors):
        tag = " [PRIMARY]" if m.is_primary else ""
        print(f"    Monitor {i}: {m.width}x{m.height} at ({m.left},{m.top}){tag}")
    if not monitors:
        print("    ERROR: No monitors detected!")
        return False

    # Test 2: Engine initialization
    print("\n[2] Testing engine initialization...")
    from monitor_shield.isolation import IsolationEngine
    engine = IsolationEngine()
    engine._monitor_cache = enumerate_monitors()
    print(f"    Engine monitors: {len(engine._monitor_cache)}")
    print("    OK")

    # Test 3: Window enumeration
    print("\n[3] Testing window enumeration...")
    windows = enumerate_windows(monitors)
    print(f"    Found {len(windows)} visible window(s):")
    for w in windows[:10]:
        print(f"      - {w.title[:50]} ({w.process_name})")
    if len(windows) > 10:
        print(f"      ... and {len(windows) - 10} more")

    # Test 4: Icon generation
    print("\n[4] Testing icon generation...")
    from monitor_shield.icon import generate_icon
    img_active = generate_icon(64, active=True)
    img_standby = generate_icon(64, active=False)
    img_conflict = generate_icon(64, active=False, conflict=True)
    print(f"    Active icon:  {img_active.size}")
    print(f"    Standby icon: {img_standby.size}")
    print(f"    Conflict icon: {img_conflict.size}")

    # Test 5: Hotkey manager
    print("\n[5] Testing hotkey manager...")
    from monitor_shield.hotkey import HotkeyManager
    hm = HotkeyManager()
    def dummy(): pass
    hm.set_callbacks(on_toggle=dummy, on_quit=dummy)
    result = hm.register()
    print(f"    Registration: {'OK' if result else 'FAILED'}")
    if result:
        hm.unregister()
        print("    Unregistration: OK")

    # Test 6: Engine toggle
    print("\n[6] Testing engine toggle...")
    engine.enable()
    print(f"    Enabled: {engine.enabled}")
    time.sleep(0.5)
    status = engine.get_status_summary()
    print(f"    Status: {status}")
    engine.disable()
    print(f"    Disabled: {not engine.enabled}")

    print("\n" + "=" * 60)
    print("  All tests completed!")
    print("=" * 60)
    return True


def info_mode():
    """Show monitor and window info and exit."""
    monitors = enumerate_monitors()
    print(f"Detected {len(monitors)} monitor(s):")
    for i, m in enumerate(monitors):
        tag = " [PRIMARY]" if m.is_primary else ""
        print(f"  Monitor {i}: {m.width}x{m.height} at ({m.left},{m.top}){tag}")

    windows = enumerate_windows(monitors)
    print(f"\nVisible windows: {len(windows)}")
    for w in windows:
        print(f"  [{w.process_name}] {w.title[:60]}")


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="MonitorShield — Full-monitor isolation for Windows"
    )
    parser.add_argument("--start-on", action="store_true", help="Start with isolation enabled")
    parser.add_argument("--test", action="store_true", help="Run component tests")
    parser.add_argument("--info", action="store_true", help="Show monitor info and exit")
    args = parser.parse_args()

    if args.test:
        success = test_mode()
        sys.exit(0 if success else 1)

    if args.info:
        info_mode()
        sys.exit(0)

    # Single instance check
    mutex = ensure_single_instance()
    if mutex is None:
        sys.exit(1)

    try:
        app = MonitorShieldApp(start_enabled=args.start_on)
        app.run()
    except Exception as ex:
        log.error("Fatal error: %s", ex, exc_info=True)
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                f"MonitorShield encountered a fatal error:\n\n{ex}",
                "MonitorShield",
                0x10,  # MB_ICONERROR
            )
        except Exception:
            pass
    finally:
        if mutex:
            ctypes.windll.kernel32.ReleaseMutex(mutex)
            ctypes.windll.kernel32.CloseHandle(mutex)


if __name__ == "__main__":
    main()
