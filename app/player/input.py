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


# R36S "GO-Super Gamepad" (SDL joystick button index -> spec button).
# Captured from the device 2026-09-12; FN/hotkey is index 16 (not 15).
JOYMAP = {
    0: "b",
    1: "a",
    2: "x",
    3: "y",
    4: "l1",
    5: "r1",
    6: "l2",
    7: "r2",
    8: "up",
    9: "down",
    10: "left",
    11: "right",
    12: "select",
    13: "start",
    16: "fn",
}

# Left analog stick axes -> direction when pushed past the deadzone.
JOY_AXES = {
    0: {True: "left", False: "right"},
    1: {True: "up", False: "down"},
}


def button_for_joy(button_index):
    """Map an SDL joystick button index to a spec button or ``None``."""
    return JOYMAP.get(button_index)


def direction_for_axis(axis, value, threshold=0.6):
    """Map a left-stick axis value past ``threshold`` to a spec direction."""
    mapping = JOY_AXES.get(axis)
    if not mapping or abs(value) < threshold:
        return None
    return mapping[value < 0]
