"""
MonitorShield - Dynamic tray icon renderer.

Generates a beautiful shield icon for the system tray with three states:
  - Active (green):  isolation is ON
  - Standby (amber): isolation is OFF
  - Conflict (red):  a cross-monitor event was blocked

All icons are drawn programmatically with Pillow at 2x resolution and
downsampled with LANCZOS for crisp rendering at any tray size.
"""

from PIL import Image, ImageDraw
import math


def _lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def generate_icon(size=64, active=True, conflict=False, frame=0):
    """Generate a shield tray icon.

    Args:
        size:     Target icon size in pixels (16–64 typical for tray).
        active:   True = green shield (isolation ON).
        conflict: True = red shield (conflict flash). Overrides active colour.
        frame:    Animation frame number for subtle pulse effect.

    Returns:
        PIL Image in RGBA mode with transparent background.
    """
    rs = size * 2  # render at 2× for anti-aliasing
    cx, cy = rs // 2, rs // 2

    img = Image.new("RGBA", (rs, rs), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ── Colour palette ──────────────────────────────────────────────────
    if conflict:
        fill      = (220, 38, 38, 255)       # red-600
        fill_lt   = (248, 113, 113, 200)     # red-400
        border    = (153, 27, 27, 255)       # red-800
        mark_char = "!"
        dot_clr   = (220, 38, 38, 255)
    elif active:
        fill      = (34, 197, 94, 255)       # emerald-500
        fill_lt   = (74, 222, 128, 200)      # emerald-400
        border    = (22, 101, 52, 255)       # emerald-800
        mark_char = "✓"
        dot_clr   = (220, 38, 38, 255)       # red status dot
    else:
        fill      = (245, 158, 11, 255)      # amber-500
        fill_lt   = (252, 211, 77, 200)      # amber-300
        border    = (180, 83, 9, 255)        # amber-700
        mark_char = "×"
        dot_clr   = (107, 114, 128, 255)     # gray status dot

    # ── Subtle pulse ────────────────────────────────────────────────────
    pulse = 1.0 + 0.012 * math.sin(frame * 0.35)
    s = rs * 0.38 * pulse  # half-size of shield body

    # ── Shield body ─────────────────────────────────────────────────────
    shield_pts = [
        (cx - s * 0.95, cy - s * 0.65),    # top-left
        (cx + s * 0.95, cy - s * 0.65),    # top-right
        (cx + s * 1.00, cy - s * 0.20),    # right upper
        (cx + s * 0.65, cy + s * 0.45),    # right mid
        (cx,            cy + s * 1.05),     # bottom point
        (cx - s * 0.65, cy + s * 0.45),    # left mid
        (cx - s * 1.00, cy - s * 0.20),    # left upper
    ]

    # Glow behind shield (3 layers)
    for i in range(3, 0, -1):
        glow_pts = [
            (x + (1 if x > cx else -1) * i * 0.8,
             y + (1 if y > cy else -1) * i * 0.8)
            for x, y in shield_pts
        ]
        draw.polygon(glow_pts, fill=(*fill[:3], 25 + i * 8))

    # Main shield fill
    draw.polygon(shield_pts, fill=fill, outline=border)

    # Inner highlight (top-left shine)
    highlight_pts = [
        (cx - s * 0.60, cy - s * 0.50),
        (cx + s * 0.10, cy - s * 0.50),
        (cx + s * 0.10, cy + s * 0.10),
        (cx - s * 0.60, cy - s * 0.10),
    ]
    draw.polygon(highlight_pts, fill=fill_lt)

    # ── Status mark ─────────────────────────────────────────────────────
    lw = max(2, rs // 28)
    mark_clr = (255, 255, 255, 240)

    if mark_char == "✓":
        # Checkmark
        check_pts = [
            (cx - s * 0.50, cy - s * 0.05),
            (cx - s * 0.15, cy + s * 0.35),
            (cx + s * 0.55, cy - s * 0.30),
        ]
        draw.line(check_pts, fill=mark_clr, width=lw, joint="curve")
    elif mark_char == "×":
        # X mark
        off = s * 0.28
        draw.line([(cx - off, cy - off), (cx + off, cy + off)], fill=mark_clr, width=lw)
        draw.line([(cx + off, cy - off), (cx - off, cy + off)], fill=mark_clr, width=lw)
    else:
        # Exclamation mark (conflict)
        bar_top = (cx, cy - s * 0.40)
        bar_bot = (cx, cy + s * 0.05)
        draw.line([bar_top, bar_bot], fill=mark_clr, width=lw + 1)
        dot_y = cy + s * 0.30
        dr = max(2, rs // 32)
        draw.ellipse([cx - dr, dot_y - dr, cx + dr, dot_y + dr], fill=mark_clr)

    # ── Status dot (top-right corner) ───────────────────────────────────
    dr = max(3, rs // 16)
    dx = cx + int(s * 0.72)
    dy = cy - int(s * 0.55)
    draw.ellipse([dx - dr, dy - dr, dx + dr, dy + dr], fill=dot_clr)

    # ── Downsample ──────────────────────────────────────────────────────
    img = img.resize((size, size), Image.LANCZOS)
    return img


def generate_icon_set(size=64):
    """Generate all three icon states at once."""
    return {
        "active":   generate_icon(size, active=True),
        "standby":  generate_icon(size, active=False),
        "conflict": generate_icon(size, active=False, conflict=True),
    }
