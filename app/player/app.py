"""The player event loop: wires the state machine to pygame.

See SPEC.md §5.3. This is the only module that runs the main loop; the
logic it drives (:mod:`app.player.stack`, :mod:`screens`, :mod:`input`) is
pure and unit-tested without pygame.
"""

import pygame

from app.player.audio import AudioManager
from app.player.input import button_for_key
from app.player.render import HEIGHT, WIDTH, Renderer
from app.player.screens import ScreenState
from app.player.stack import NavigationStack
from app.player.theme import Theme
from app.player.video import VideoPlayer

FPS = 30
FADE_SECONDS = 0.22
DEFAULT_WINDOW = (960, 720)


class Player:
    def __init__(self, package, window=None, no_video=False,
                 sync_callback=None):
        self.package = package
        self.window_size = window or DEFAULT_WINDOW
        self.no_video = no_video
        self.sync_callback = sync_callback

        self.theme = Theme(package.manifest.get("theme"))
        self.renderer = Renderer(package, self.theme)
        self.audio = AudioManager()
        self.video = VideoPlayer(enabled=not no_video)

        self.stack = NavigationStack(package.root)
        self.state = None
        self.running = False
        self.status = ""

        self._canvas = None
        self._display = None
        self._clock = None
        self._prev_canvas = None
        self._fade = None       # dict(t=..., duration=...)
        self._video_pending = False

    # -- lifecycle -------------------------------------------------------

    def run(self):
        pygame.init()
        self._canvas = pygame.Surface((WIDTH, HEIGHT))
        try:
            self._display = pygame.display.set_mode(self.window_size)
        except pygame.error:
            self._display = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption(self.package.title or "r36s-disp")
        self._clock = pygame.time.Clock()
        self.audio.init()

        self.running = True
        self._enter(self.stack.current)
        while self.running:
            dt = self._clock.tick(FPS) / 1000.0
            self._pump_events()
            self._step(dt)
        self.audio.shutdown()
        pygame.quit()

    def _pump_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    continue
                name = _key_name(event.key)
                button = button_for_key(name)
                if button:
                    self._apply(self.state.resolve(button))

    def _step(self, dt):
        if not self.running:
            return
        if self._video_pending:
            self._video_pending = False
            self.audio.stop()
            self.video.play(self.package.asset(self.state.screen["video"]),
                            self.state.screen["video"])
            self._apply(self.state.advance())
            return

        action = self.state.tick(dt)
        if action:
            self._apply(action)

        self._update_fade(dt)
        self._render()

    # -- navigation ------------------------------------------------------

    def _enter(self, sid):
        if sid not in self.package.screens:
            return
        screen = self.package.screens[sid]
        if self.state is not None and self._canvas is not None:
            self._prev_canvas = self._canvas.copy()
            transition = screen.get("transition", "fade")
            if transition == "fade":
                self._fade = {"t": 0.0, "duration": FADE_SECONDS}
            else:
                self._fade = None

        self.state = ScreenState(self.package, sid)
        self.audio.stop()
        audio = self.state.audio
        if audio:
            self.audio.play(audio, self.package.asset(audio),
                            loop=self.state.audio_loop)
        self._video_pending = (self.state.type == "video")

    def _apply(self, action):
        if action is None:
            return
        kind = action.kind
        if kind == "goto":
            self._goto(action.target, replace=False)
        elif kind == "next":
            if action.target:
                self._goto(action.target, replace=True)
            else:
                self._back()
        elif kind == "back":
            self._back()
        elif kind == "home":
            target = self.stack.home()
            self._enter(target)
        elif kind == "sync":
            self._do_sync()
        elif kind == "exit":
            self.running = False

    def _goto(self, sid, replace):
        if sid not in self.package.screens:
            return
        if replace:
            self.stack.replace(sid)
        else:
            self.stack.push(sid)
        self._enter(sid)

    def _back(self):
        if self.stack.depth > 1:
            self.stack.pop()
            self._enter(self.stack.current)

    def _do_sync(self):
        if self.sync_callback:
            try:
                self.status = self.sync_callback() or ""
            except Exception as exc:  # sync must never kill the player
                self.status = "sync failed: %s" % exc
        else:
            self.status = "sync unavailable in this build"

    # -- rendering -------------------------------------------------------

    def _update_fade(self, dt):
        if self._fade:
            self._fade["t"] += dt
            if self._fade["t"] >= self._fade["duration"]:
                self._fade = None
                self._prev_canvas = None

    def _render(self):
        self.renderer.draw(self._canvas, self.state, footer=self._footer())

        frame = self._canvas
        if self._fade and self._prev_canvas is not None:
            alpha = int(255 * min(1.0, self._fade["t"] / self._fade["duration"]))
            frame = self._prev_canvas.copy()
            self._canvas.set_alpha(alpha)
            frame.blit(self._canvas, (0, 0))
            self._canvas.set_alpha(255)

        self._blit_scaled(frame)
        pygame.display.flip()

    def _blit_scaled(self, frame):
        dw, dh = self._display.get_size()
        scale = min(dw / WIDTH, dh / HEIGHT)
        size = (max(1, int(WIDTH * scale)), max(1, int(HEIGHT * scale)))
        if size == (WIDTH, HEIGHT):
            scaled = frame
        else:
            scaled = pygame.transform.smoothscale(frame, size)
        self._display.fill((0, 0, 0))
        self._display.blit(scaled, scaled.get_rect(
            center=(dw // 2, dh // 2)))

    def _footer(self):
        package = self.package.package
        parts = [str(package.get("title", ""))]
        date = package.get("date")
        if date:
            parts.append(str(date))
        if self.status:
            parts.append(self.status)
        return "   ".join(p for p in parts if p)


def _key_name(key):
    try:
        return pygame.key.name(key)
    except (ValueError, pygame.error):
        return ""
