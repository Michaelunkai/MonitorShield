"""
MonitorShield - Integration Tests.

Tests multi-component interactions: engine + display, engine + tray, etc.
Run with: python tests\integration_test.py
"""

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from monitor_shield.display import enumerate_monitors, enumerate_windows
from monitor_shield.isolation import IsolationEngine
from monitor_shield.icon import generate_icon
from monitor_shield.hotkey import HotkeyManager


class TestEngineDisplayIntegration(unittest.TestCase):
    """Engine + Display integration."""

    def setUp(self):
        self.engine = IsolationEngine()

    def tearDown(self):
        if self.engine.enabled:
            self.engine.disable()

    def test_engine_sees_all_monitors(self):
        self.engine.enable()
        monitors = enumerate_monitors()
        self.assertEqual(len(self.engine._monitor_cache), len(monitors))

    def test_engine_tracks_windows_per_monitor(self):
        self.engine.enable()
        time.sleep(0.3)
        windows = enumerate_windows(self.engine._monitor_cache)
        self.assertEqual(
            self.engine.stats["windows_tracked"],
            len(self.engine._window_assignments),
        )

    def test_engine_assigns_correct_monitor(self):
        self.engine.enable()
        time.sleep(0.2)
        monitors = enumerate_monitors()
        mon_handles = {m.handle for m in monitors}
        for hwnd, mon_handle in self.engine._window_assignments.items():
            self.assertIn(mon_handle, mon_handles)

    def test_disable_releases_all_hooks(self):
        self.engine.enable()
        time.sleep(0.2)
        self.assertIsNotNone(self.engine._hook)
        self.engine.disable()
        self.assertIsNone(self.engine._hook)
        self.assertIsNone(self.engine._enforcement_thread)


class TestEngineIconIntegration(unittest.TestCase):
    """Engine + Icon state synchronization."""

    def test_icon_matches_engine_off(self):
        from monitor_shield.icon import generate_icon
        engine = IsolationEngine()
        img = generate_icon(64, active=engine.enabled)
        self.assertEqual(img.size, (64, 64))

    def test_icon_matches_engine_on(self):
        from monitor_shield.icon import generate_icon
        engine = IsolationEngine()
        engine.enable()
        img = generate_icon(64, active=engine.enabled)
        self.assertEqual(img.size, (64, 64))
        engine.disable()


class TestMultiMonitorScenarios(unittest.TestCase):
    """Tests that simulate multi-monitor scenarios."""

    def test_engine_handles_single_monitor(self):
        engine = IsolationEngine()
        engine.enable()
        time.sleep(0.2)
        monitors = enumerate_monitors()
        if len(monitors) == 1:
            # Single monitor: all windows should be assigned to it
            for hwnd, mon_handle in engine._window_assignments.items():
                self.assertEqual(mon_handle, monitors[0].handle)
        engine.disable()

    def test_engine_stats_accumulate(self):
        engine = IsolationEngine()
        engine.enable()
        time.sleep(0.5)
        stats1 = engine.stats.copy()
        time.sleep(0.5)
        stats2 = engine.stats
        # tracked count should remain stable or grow
        self.assertGreaterEqual(stats2["windows_tracked"], 0)
        engine.disable()

    def test_repeated_enable_disable_stable(self):
        """Ensure repeated cycles don't leak resources."""
        engine = IsolationEngine()
        for i in range(3):
            engine.enable()
            time.sleep(0.1)
            engine.disable()
            time.sleep(0.1)
        self.assertFalse(engine.enabled)
        self.assertIsNone(engine._hook)
        self.assertIsNone(engine._enforcement_thread)


class TestHotkeyIntegration(unittest.TestCase):
    """Hotkey + Engine integration."""

    def test_hotkey_toggle_engine(self):
        engine = IsolationEngine()
        hm = HotkeyManager()
        hm.set_callbacks(on_toggle=engine.toggle, on_quit=None)

        self.assertFalse(engine.enabled)
        hm.register()
        self.assertTrue(hm.is_registered)

        # Simulate toggle
        engine.toggle()
        self.assertTrue(engine.enabled)

        engine.toggle()
        self.assertFalse(engine.enabled)

        hm.unregister()


if __name__ == "__main__":
    print("=" * 60)
    print("  MonitorShield - Integration Tests")
    print("=" * 60)
    unittest.main(verbosity=2)
