"""Video playback via an ``mpv`` subprocess (SPEC.md §3.3 / §5.3).

The player stops its own audio before playback and resumes state after.
If ``mpv`` is unavailable (e.g. desktop dev box) or playback is disabled,
``play`` logs once and returns immediately so the state machine advances.
"""

import os
import shutil
import subprocess
import tempfile


def _default_runner(argv):
    return subprocess.run(argv)


class VideoPlayer:
    MPV_ARGS = (
        "--really-quiet",
        "--fullscreen",
        "--no-osc",
        "--no-input-default-bindings",
        "--force-window=yes",
    )

    def __init__(self, enabled=True, runner=None, which=None):
        self.enabled = enabled
        self._runner = runner or _default_runner
        self._which = which or shutil.which
        self._warned = False

    def available(self):
        return bool(self.enabled and self._which("mpv"))

    def play(self, data, name="video"):
        """Play raw file bytes full-screen. Returns ``"ended"`` or ``"input"``."""
        if not self.available():
            if not self._warned:
                print("warning: mpv unavailable; skipping video %r" % name)
                self._warned = True
            return "ended"

        fd, path = tempfile.mkstemp(suffix=".mp4", prefix="r36s-video-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            argv = ["mpv"] + list(self.MPV_ARGS) + [path]
            try:
                self._runner(argv)
            except OSError as exc:
                if not self._warned:
                    print("warning: mpv failed (%s); skipping video" % exc)
                    self._warned = True
            return "ended"
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
