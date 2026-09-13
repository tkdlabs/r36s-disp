"""Package server for the r36s daily-content player (SPEC.md §4, §7).

Server-side only; never imported by the device app.
"""

import os

DEFAULT_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store")
