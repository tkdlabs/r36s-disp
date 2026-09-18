"""Built-in dark theme plus manifest overrides (SPEC.md §3.2).

Color values may be CSS-ish hex strings (``"#rrggbb"`` / ``"#rrggbbaa"``) or
``[r, g, b]`` / ``[r, g, b, a]`` sequences.
"""

import os

import pygame

# Bundled font (OFL Noto Sans); falls back to pygame's default if missing.
FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fonts", "NotoSans-Regular.ttf")

DEFAULTS = {
    "bg": (18, 18, 22, 255),
    "fg": (235, 235, 235, 255),
    "accent": (90, 160, 255, 255),
    "muted": (150, 150, 160, 255),
    "selection_bg": (40, 70, 120, 255),
    "caption_bg": (0, 0, 0, 170),
    "font_scale": 1.0,
}

# Base pixel sizes at 640x480; multiplied by theme font_scale.
BASE_SIZES = {
    "title": 34,
    "subtitle": 20,
    "item": 24,
    "detail": 17,
    "body": 22,
    "caption": 20,
}


def parse_color(value):
    """Parse a manifest color into an RGBA tuple, or return None."""
    if isinstance(value, (list, tuple)):
        parts = list(value)
        if len(parts) == 3:
            parts.append(255)
        if len(parts) == 4 and all(isinstance(p, int) for p in parts):
            return tuple(max(0, min(255, int(p))) for p in parts)
        return None
    if isinstance(value, str):
        s = value.strip().lstrip("#")
        if len(s) in (6, 8):
            try:
                channels = [int(s[i:i + 2], 16) for i in range(0, len(s), 2)]
            except ValueError:
                return None
            if len(channels) == 3:
                channels.append(255)
            return tuple(channels)
    return None


class Theme:
    def __init__(self, overrides=None):
        self._colors = {}
        for name in ("bg", "fg", "accent", "muted", "selection_bg", "caption_bg"):
            parsed = parse_color((overrides or {}).get(name))
            self._colors[name] = parsed or DEFAULTS[name]
        scale = (overrides or {}).get("font_scale", DEFAULTS["font_scale"])
        self.font_scale = float(scale) if isinstance(scale, (int, float)) else 1.0
        self._fonts = {}

    @property
    def bg(self):
        return self._colors["bg"]

    @property
    def fg(self):
        return self._colors["fg"]

    @property
    def accent(self):
        return self._colors["accent"]

    @property
    def muted(self):
        return self._colors["muted"]

    @property
    def selection_bg(self):
        return self._colors["selection_bg"]

    @property
    def caption_bg(self):
        return self._colors["caption_bg"]

    def font(self, role):
        """Return a cached ``pygame.font.Font`` for a role (title/item/...)."""
        if role not in self._fonts:
            size = max(8, int(BASE_SIZES.get(role, BASE_SIZES["body"])
                              * self.font_scale))
            self._fonts[role] = _load_font(size)
        return self._fonts[role]


def _load_font(size):
    if os.path.isfile(FONT_PATH):
        try:
            return pygame.font.Font(FONT_PATH, size)
        except (OSError, pygame.error):
            pass
    return pygame.font.Font(None, size)
