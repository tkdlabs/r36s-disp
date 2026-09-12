"""Background audio via ``pygame.mixer`` (SPEC.md §3.3 / §5.3).

One track at a time. All failures are non-fatal: the player keeps running
silently if the mixer or a codec is unavailable.
"""

import io

import pygame


class AudioManager:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self._ready = False
        self.current = None
        self._warned = False

    def init(self):
        if not self.enabled:
            return False
        try:
            pygame.mixer.init()
            self._ready = True
        except pygame.error:
            self._ready = False
        return self._ready

    def play(self, name, data, loop=False):
        """Start ``data`` (raw file bytes) as the single active track."""
        self.stop()
        if not self.enabled or not self._ready or data is None:
            return False
        try:
            sound = pygame.mixer.Sound(file=io.BytesIO(data))
            sound.play(loops=-1 if loop else 0)
        except (pygame.error, ValueError):
            if not self._warned:
                print("warning: could not play audio %r" % name)
                self._warned = True
            return False
        self.current = name
        return True

    def stop(self):
        if self._ready:
            try:
                pygame.mixer.stop()
            except pygame.error:
                pass
        self.current = None

    def shutdown(self):
        self.stop()
        if self._ready:
            try:
                pygame.mixer.quit()
            except pygame.error:
                pass
            self._ready = False
