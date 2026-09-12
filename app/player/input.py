"""Desktop key mapping to the spec's normalized button names (SPEC.md §3.4).

Pure: no pygame import so this stays unit-testable everywhere.
"""

# Desktop keyboard -> spec button. Chosen so the layout roughly mirrors the
# R36S d-pad/face buttons for development without hardware.
KEYMAP = {
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "z": "a",
    "x": "b",
    "c": "x",
    "v": "y",
    "q": "l1",
    "w": "l2",
    "e": "r1",
    "r": "r2",
    "return": "start",
    "kp_enter": "start",
    "tab": "select",
    "escape": "fn",
    "space": "a",
}


def button_for_key(key_name):
    """Map a pygame key name (e.g. ``"up"``) to a spec button or ``None``."""
    if not isinstance(key_name, str):
        return None
    return KEYMAP.get(key_name.lower())
