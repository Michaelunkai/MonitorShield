"""
MonitorShield - Comprehensive Test Suite.

Tests all components: display enumeration, isolation engine, icon rendering,
hotkey manager, and integration scenarios.

Run with: python tests\full_test_suite.py
Or:       python src\monitor_shield --test (component subset)
"""

import sys
import os
import time
import unittest

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from monitor_shield.display import (
    enumerate_monitors,
    enumerate_windows,
    get_monitor_for_window,
    MonitorInfo,
    WindowInfo,
)
from monitor_shield.icon import generate_icon, generate_icon_set
from monitor_shield.isolation import IsolationEngine, ForegroundHook
from monitor_shield.hotkey import HotkeyManager


class TestMonitorEnumeration(unittest.TestCase):
    """Tests for monitor enumeration and MonitorInfo."""

    def test_enumerate_monitors_returns_list(self):
        monitors = enumerate_monitors()
        self.assertIsInstance(monitors, list)

    def test_enumerate_monitors_returns_at_least_one(self):
        monitors = enumerate_monitors()
        self.assertGreaterEqual(len(monitors), 1, "Should detect at least one monitor")

    def test_monitor_info_has_required_fields(self):
        monitors = enumerate_monitors()
        self.assertGreater(len(monitors), 0)
        m = monitors[0]
        self.assertIsInstance(m, MonitorInfo)
        self.assertIsInstance(m.handle, int)
        self.assertIsInstance(m.left, int)
        self.assertIsInstance(m.top, int)
        self.assertIsInstance(m.right, int)
        self.assertIsInstance(m.bottom, int)
        self.assertIsInstance(m.is_primary, bool)

    def test_monitor_dimensions_positive(self):
        monitors = enumerate_monitors()
        for m in monitors:
            self.assertGreater(m.width, 0, f"Monitor width should be > 0: {m}")
            self.assertGreater(m.height, 0, f"Monitor height should be > 0: {m}")

    def test_monitor_contains_point(self):
        monitors = enumerate_monitors()
        self.assertGreater(len(monitors), 0)
        m = monitors[0]
        cx, cy = m.center()
        self.assertTrue(m.contains_point(cx, cy), "Center point should be inside monitor")
        self.assertFalse(m.contains_point(m.right + 100, m.bottom + 100),
                         "Point outside monitor should not be contained")

    def test_monitor_contains_rect(self):
        monitors = enumerate_monitors()
        self.assertGreater(len(monitors), 0)
        m = monitors[0]
        self.assertTrue(m.contains_rect(m.left, m.top, m.right, m.bottom),
                        "Monitor's own rect should be contained")
        self.assertFalse(m.contains_rect(m.right, m.bottom, m.right + 100, m.bottom + 100),
                         "External rect should not be contained")

    def test_monitor_clamp_rect(self):
        monitors = enumerate_monitors()
        self.assertGreater(len(monitors), 0)
        m = monitors[0]
        x, y, w, h = m.clamp_rect(m.left - 100, m.top - 100, 200, 200)
        self.assertGreaterEqual(x, m.left)
        self.assertGreaterEqual(y, m.top)
        self.assertLessEqual(x + w, m.right)
        self.assertLessEqual(y + h, m.bottom)

    def test_one_primary_monitor(self):
        monitors = enumerate_monitors()
        primaries = [m for m in monitors if m.is_primary]
        self.assertGreaterEqual(len(primaries), 1, "Should have at least one primary monitor")

    def test_monitor_center(self):
        monitors = enumerate_monitors()
        self.assertGreater(len(monitors), 0)
        m = monitors[0]
        cx, cy = m.center()
        self.assertEqual(cx, (m.left + m.right) // 2)
        self.assertEqual(cy, (m.top + m.bottom) // 2)


class TestWindowEnumeration(unittest.TestCase):
    """Tests for window enumeration."""

    def test_enumerate_windows_returns_list(self):
        monitors = enumerate_monitors()
        windows = enumerate_windows(monitors)
        self.assertIsInstance(windows, list)

    def test_windows_have_required_fields(self):
        monitors = enumerate_monitors()
        windows = enumerate_windows(monitors)
        self.assertGreater(len(windows), 0, "Should find at least one window")
        w = windows[0]
        self.assertIsInstance(w, WindowInfo)
        self.assertIsInstance(w.hwnd, int)
        self.assertIsInstance(w.title, str)
        self.assertIsInstance(w.process_name, str)
        self.assertIsInstance(w.monitor_handle, int)
        self.assertIsInstance(w.rect, tuple)
        self.assertEqual(len(w.rect), 4)

    def test_all_windows_on_known_monitor(self):
        monitors = enumerate_monitors()
        mon_handles = {m.handle for m in monitors}
        windows = enumerate_windows(monitors)
        for w in windows:
            self.assertIn(w.monitor_handle, mon_handles,
                          f"Window '{w.title[:30]}' on unknown monitor {w.monitor_handle}")

    def test_window_rect_reasonable(self):
        monitors = enumerate_monitors()
        windows = enumerate_windows(monitors)
        for w in windows[:20]:  # sample first 20
            left, top, right, bottom = w.rect
            self.assertLess(left, right, f"Window {w.hwnd}: left >= right")
            self.assertLess(top, bottom, f"Window {w.hwnd}: top >= bottom")


class TestIconGeneration(unittest.TestCase):
    """Tests for tray icon generation."""

    def test_generate_active_icon(self):
        img = generate_icon(64, active=True)
        self.assertEqual(img.size, (64, 64))
        self.assertEqual(img.mode, "RGBA")

    def test_generate_standby_icon(self):
        img = generate_icon(64, active=False)
        self.assertEqual(img.size, (64, 64))
        self.assertEqual(img.mode, "RGBA")

    def test_generate_conflict_icon(self):
        img = generate_icon(64, active=False, conflict=True)
        self.assertEqual(img.size, (64, 64))
        self.assertEqual(img.mode, "RGBA")

    def test_icon_set(self):
        icons = generate_icon_set(64)
        self.assertIn("active", icons)
        self.assertIn("standby", icons)
        self.assertIn("conflict", icons)
        for img in icons.values():
            self.assertEqual(img.size, (64, 64))

    def test_icon_different_sizes(self):
        for size in [16, 20, 24, 32, 48, 64]:
            img = generate_icon(size, active=True)
            self.assertEqual(img.size, (size, size))

    def test_icon_not_blank(self):
        """Verify the icon has non-transparent pixels (is actually drawn)."""
        img = generate_icon(64, active=True)
        pixels = list(img.getdata())
        non_transparent = [p for p in pixels if p[3] > 0]
        self.assertGreater(len(non_transparent), 100, "Icon should have visible pixels")

    def test_icon_frame_variation(self):
        """Different frames should produce different images (pulse effect)."""
        img1 = generate_icon(64, active=True, frame=0)
        img2 = generate_icon(64, active=True, frame=50)
        # They should be different due to pulse
        data1 = list(img1.getdata())
        data2 = list(img2.getdata())
        self.assertNotEqual(data1, data2, "Different frames should produce different icons")


class TestIsolationEngine(unittest.TestCase):
    """Tests for the core isolation engine."""

    def setUp(self):
        self.engine = IsolationEngine()

    def test_initially_disabled(self):
        self.assertFalse(self.engine.enabled)

    def test_enable_disable_cycle(self):
        self.engine.enable()
        self.assertTrue(self.engine.enabled)
        time.sleep(0.2)
        self.engine.disable()
        self.assertFalse(self.engine.enabled)

    def test_toggle(self):
        self.assertFalse(self.engine.enabled)
        self.engine.toggle()
        self.assertTrue(self.engine.enabled)
        self.engine.toggle()
        self.assertFalse(self.engine.enabled)

    def test_stats_reset_on_disable(self):
        self.engine.enable()
        time.sleep(0.3)
        self.engine.disable()
        stats = self.engine.stats
        self.assertEqual(stats["windows_tracked"], 0)
        self.assertEqual(stats["moves_blocked"], 0)

    def test_status_summary_off(self):
        self.assertEqual(self.engine.get_status_summary(), "Isolation: OFF")

    def test_status_summary_on(self):
        self.engine.enable()
        status = self.engine.get_status_summary()
        self.assertIn("Isolation: ON", status)
        self.assertIn("monitor(s)", status)
        self.engine.disable()

    def test_monitor_info_text(self):
        info = self.engine.get_monitor_info_text()
        self.assertIn("Monitor", info)

    def test_enable_assigns_windows(self):
        self.engine.enable()
        time.sleep(0.2)
        self.assertGreater(self.engine.stats["windows_tracked"], 0)
        self.engine.disable()

    def test_state_changed_callback(self):
        states = []
        self.engine.on_state_changed(lambda enabled: states.append(enabled))
        self.engine.enable()
        time.sleep(0.1)
        self.engine.disable()
        time.sleep(0.1)
        self.assertIn(True, states)
        self.assertIn(False, states)

    def test_event_callback(self):
        events = []
        self.engine.on_event(lambda msg: events.append(msg))
        self.engine.enable()
        time.sleep(0.2)
        self.assertTrue(len(events) > 0, "Should have received at least one event")
        self.engine.disable()


class TestHotkeyManager(unittest.TestCase):
    """Tests for the hotkey manager."""

    def setUp(self):
        self.hm = HotkeyManager()
        self.toggled = False
        self.quitted = False
        self.hm.set_callbacks(
            on_toggle=lambda: setattr(self, 'toggled', True),
            on_quit=lambda: setattr(self, 'quitted', True),
        )

    def tearDown(self):
        self.hm.unregister()

    def test_register(self):
        result = self.hm.register()
        self.assertTrue(result)
        self.assertTrue(self.hm.is_registered)

    def test_unregister(self):
        self.hm.register()
        self.hm.unregister()
        self.assertFalse(self.hm.is_registered)

    def test_double_register(self):
        self.assertTrue(self.hm.register())
        self.assertTrue(self.hm.register())  # Should not fail

    def test_unregister_when_not_registered(self):
        self.hm.unregister()  # Should not fail


class TestIntegration(unittest.TestCase):
    """Integration tests combining multiple components."""

    def test_full_lifecycle(self):
        """Test complete lifecycle: create engine → enable → verify → disable."""
        engine = IsolationEngine()
        events = []
        engine.on_event(lambda msg: events.append(msg))

        engine.enable()
        self.assertTrue(engine.enabled)
        time.sleep(0.3)

        monitors = enumerate_monitors()
        self.assertGreater(len(monitors), 0)

        windows = enumerate_windows(monitors)
        self.assertGreater(len(windows), 0)

        stats = engine.stats
        self.assertGreater(stats["windows_tracked"], 0)

        engine.disable()
        self.assertFalse(engine.enabled)

    def test_rapid_toggle(self):
        """Test rapid enable/disable cycles don't crash."""
        engine = IsolationEngine()
        for _ in range(5):
            engine.enable()
            time.sleep(0.05)
            engine.disable()
            time.sleep(0.05)
        self.assertFalse(engine.enabled)

    def test_icon_and_engine_sync(self):
        """Test that icon state matches engine state."""
        from monitor_shield.icon import generate_icon
        engine = IsolationEngine()

        # Off state
        self.assertFalse(engine.enabled)
        img_off = generate_icon(64, active=False)
        self.assertEqual(img_off.size, (64, 64))

        # On state
        engine.enable()
        self.assertTrue(engine.enabled)
        img_on = generate_icon(64, active=True)
        self.assertEqual(img_on.size, (64, 64))

        engine.disable()


if __name__ == "__main__":
    print("=" * 60)
    print("  MonitorShield - Full Test Suite")
    print("=" * 60)
    unittest.main(verbosity=2)
