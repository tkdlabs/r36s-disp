"""Per-screen state machine: timing, scrolling, input resolution.

Pure logic (no pygame), driven by an injected ``dt`` so behavior is
deterministic and testable. Rendering lives in :mod:`app.player.render`.
"""

from collections import namedtuple

# Action.kind values:
#   "goto"    push target screen id
#   "next"    auto-advance: replace with target, or pop if target is None
#   "back"    pop the navigation stack
#   "home"    reset to the package root
#   "sync"    trigger a sync (app-level stub in M2)
#   "exit"    quit the player
Action = namedtuple("Action", "kind target")
Action.__new__.__defaults__ = (None,)

# Default media slide duration when a slide omits one (SPEC.md §3.3).
DEFAULT_SLIDE_DURATION = 5.0

MEDIA_TYPES = ("image", "slideshow", "video")
READ_TYPES = ("menu", "list", "text")

_TERMINAL_ACTIONS = ("back", "home", "sync", "exit")


class ScreenState:
    """Mutable runtime state for a single screen."""

    def __init__(self, package, sid, page_size=8):
        try:
            screen = package.screens[sid]
        except KeyError:
            raise KeyError("unknown screen %r" % sid)
        self.package = package
        self.sid = sid
        self.screen = screen
        self.type = screen.get("type")
        self.page_size = max(1, int(page_size))

        self.elapsed = 0.0
        self.index = 0          # menu selection / generic cursor
        self.scroll = 0         # list/text line offset
        self.slide_index = 0
        self.slide_elapsed = 0.0

    # -- collections -----------------------------------------------------

    @property
    def items(self):
        if self.type == "menu" or self.type == "list":
            return self.screen.get("items") or []
        if self.type == "slideshow":
            return self.screen.get("slides") or []
        if self.type == "text":
            return self.screen.get("body", "").split("\n")
        return []

    @property
    def count(self):
        return len(self.items)

    # -- timing ----------------------------------------------------------

    def tick(self, dt):
        """Advance time by ``dt`` seconds, returning an ``Action`` or None."""
        if dt < 0:
            dt = 0.0
        self.elapsed += dt

        if self.type == "slideshow":
            return self._tick_slideshow(dt)

        duration = self.screen.get("duration")
        if duration is not None and self.elapsed >= duration:
            return self.advance()
        return None

    def _tick_slideshow(self, dt):
        slides = self.items
        if not slides:
            return None
        self.slide_elapsed += dt
        while self.slide_index < len(slides):
            slide = slides[self.slide_index]
            dur = slide.get("duration", DEFAULT_SLIDE_DURATION)
            if self.slide_elapsed < dur:
                return None
            self.slide_elapsed -= dur
            self.slide_index += 1
        return self.advance()

    # -- navigation helpers ---------------------------------------------

    def advance(self):
        """Go forward: ``next`` if declared, otherwise back."""
        return Action("next", self.screen.get("next"))

    def _move(self, delta, total):
        if total <= 0:
            return
        self.index = max(0, min(total - 1, self.index + delta))

    def _scroll(self, delta, total):
        if total <= 0:
            return
        self.scroll = max(0, min(total - 1, self.scroll + delta))

    # -- slide / scroll controls ----------------------------------------

    def next_slide(self):
        slides = self.items
        if self.slide_index < len(slides) - 1:
            self.slide_index += 1
            self.slide_elapsed = 0.0
        else:
            return self.advance()
        return None

    def prev_slide(self):
        if self.slide_index > 0:
            self.slide_index -= 1
            self.slide_elapsed = 0.0
        return None

    # -- input resolution -----------------------------------------------

    def resolve(self, button):
        """Resolve a button to an ``Action`` (overrides, then defaults)."""
        overrides = self.screen.get("inputs") or {}
        if button in overrides:
            return self._from_value(overrides[button])

        if button == "b":
            return Action("back")
        if button == "select":
            return Action("sync")
        if button == "fn":
            return Action("exit")
        if button == "start":
            if self.type in READ_TYPES:
                return Action("home")
            # Media: skip to end (advance) per SPEC §3.4.
            return self.advance()

        if self.type == "menu":
            return self._menu_input(button)
        if self.type == "list":
            return self._list_input(button)
        if self.type == "text":
            return self._text_input(button)
        if self.type == "slideshow":
            return self._slideshow_input(button)
        if self.type == "image":
            return self._image_input(button)
        return None

    def _from_value(self, value):
        if value in _TERMINAL_ACTIONS:
            return Action(value)
        if value == "next":
            return self.advance()
        return Action("goto", value)

    def _menu_input(self, button):
        total = self.count
        if button == "up":
            self._move(-1, total)
        elif button == "down":
            self._move(1, total)
        elif button == "left":
            self._move(-self.page_size, total)
        elif button == "right":
            self._move(self.page_size, total)
        elif button == "a":
            if total <= 0:
                return None
            item = self.items[self.index]
            if "goto" in item:
                return Action("goto", item["goto"])
            action = item.get("action")
            if action == "next":
                return self.advance()
            if action in _TERMINAL_ACTIONS:
                return Action(action)
        return None

    def _list_input(self, button):
        total = self.count
        if button == "up":
            self._scroll(-1, total)
        elif button == "down":
            self._scroll(1, total)
        elif button == "left" or button == "l1":
            self._scroll(-self.page_size, total)
        elif button == "right" or button == "r1":
            self._scroll(self.page_size, total)
        elif button == "a":
            return self.advance()
        return None

    def _text_input(self, button):
        lines = self.items
        self._scroll(0, len(lines))
        total = len(lines)
        if button == "up":
            self._scroll(-1, total)
        elif button == "down":
            self._scroll(1, total)
        elif button == "left" or button == "l1":
            self._scroll(-self.page_size, total)
        elif button == "right" or button == "r1":
            self._scroll(self.page_size, total)
        elif button == "a":
            return self.advance()
        return None

    def _slideshow_input(self, button):
        if button == "a":
            return self.next_slide()
        if button == "l1":
            return self.prev_slide()
        if button == "r1":
            return self.next_slide()
        return None

    def _image_input(self, button):
        if button == "a":
            return self.advance()
        if button == "l1":
            return Action("back")
        return None

    # -- audio -----------------------------------------------------------

    @property
    def audio(self):
        return self.screen.get("audio")

    @property
    def audio_loop(self):
        return bool(self.screen.get("audio_loop", False))
