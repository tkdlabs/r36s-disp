"""First-run marker for the controls overlay (SPEC.md §5.3).

A small flag file under the data dir records that the player has shown its
control hints once, so the overlay only appears on the very first launch.
Stdlib only, Python 3.8+; a missing or unwritable marker never breaks play.
"""

import os

MARKER_NAME = ".controls-seen"


def marker_path(data_dir):
    return os.path.join(data_dir, MARKER_NAME)


def controls_seen(data_dir):
    """Return True once the controls overlay has been shown."""
    return os.path.isfile(marker_path(data_dir))


def mark_controls_seen(data_dir):
    """Best-effort record that the overlay was shown; never raises."""
    try:
        os.makedirs(data_dir, exist_ok=True)
        with open(marker_path(data_dir), "w", encoding="utf-8") as fh:
            fh.write("1\n")
    except OSError:
        pass
