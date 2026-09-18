"""pygame renderers for every screen type (SPEC.md §3.3).

Everything draws to a fixed 640x480 logical surface; the player scales that
to the real display mode at runtime (§5.3).
"""

import io

import pygame

WIDTH = 640
HEIGHT = 480
MARGIN = 24
TITLE_TOP = 20
BODY_TOP = 96
FOOTER_H = 26
ITEM_H = 50
SLIDE_DOT_R = 5

# Desktop key -> spec button (SPEC.md §3.4). Shown once on first run.
CONTROL_HINTS = (
    ("Arrows", "D-pad"),
    ("Z / X", "A / B"),
    ("C / V", "X / Y"),
    ("Q / E", "L1 / R1"),
    ("Enter", "Start"),
    ("R-Shift / Tab", "Select (sync)"),
    ("Esc", "Quit"),
)


def wrap_text(font, text, max_width):
    """Greedy word-wrap returning a list of lines (never empty)."""
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = word if not current else current + " " + word
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


class Renderer:
    def __init__(self, package, theme):
        self.package = package
        self.theme = theme
        self._images = {}

    # -- image cache -----------------------------------------------------

    def _surface(self, path):
        if path not in self._images:
            data = self.package.asset(path)
            try:
                surf = pygame.image.load(io.BytesIO(data))
            except pygame.error:
                surf = None
            else:
                surf = surf.convert_alpha()
            self._images[path] = surf
        return self._images[path]

    # -- entry point -----------------------------------------------------

    def draw(self, canvas, state, footer=None):
        canvas.fill(self.theme.bg)
        handler = {
            "menu": self._draw_menu,
            "list": self._draw_list,
            "image": self._draw_image,
            "video": self._draw_video,
            "text": self._draw_text,
            "slideshow": self._draw_slideshow,
            "notice": self._draw_notice,
        }.get(state.type)
        if handler:
            handler(canvas, state)
        else:
            self.message(canvas, "Unsupported screen type: %r" % state.type)
        if footer:
            self._draw_footer(canvas, footer)

    # -- shared chrome ---------------------------------------------------

    def _draw_footer(self, canvas, text):
        font = self.theme.font("detail")
        surf = font.render(text, True, self.theme.muted)
        rect = surf.get_rect()
        rect.bottomleft = (MARGIN, HEIGHT - 8)
        canvas.blit(surf, rect)

    def _draw_title(self, canvas, text, subtitle=None):
        y = TITLE_TOP
        if text:
            title = self.theme.font("title").render(text, True, self.theme.fg)
            canvas.blit(title, (MARGIN, y))
            y += title.get_height() + 6
        if subtitle:
            sub = self.theme.font("subtitle").render(
                subtitle, True, self.theme.muted)
            canvas.blit(sub, (MARGIN, y))

    def _draw_caption(self, canvas, text):
        if not text:
            return
        font = self.theme.font("caption")
        lines = wrap_text(font, text, WIDTH - 2 * MARGIN)
        height = sum(font.get_linesize() for _ in lines) + 16
        bar = pygame.Surface((WIDTH, height), pygame.SRCALPHA)
        bar.fill(self.theme.caption_bg)
        canvas.blit(bar, (0, HEIGHT - height))
        y = HEIGHT - height + 8
        for line in lines:
            surf = font.render(line, True, self.theme.fg)
            canvas.blit(surf, (MARGIN, y))
            y += font.get_linesize()

    # -- menu ------------------------------------------------------------

    def _draw_menu(self, canvas, state):
        self._draw_title(canvas, state.screen.get("title"),
                         state.screen.get("subtitle"))
        items = state.items
        if not items:
            return
        font = self.theme.font("item")
        detail_font = self.theme.font("detail")
        top = BODY_TOP
        visible = max(1, (HEIGHT - top - FOOTER_H - 8) // ITEM_H)
        start = max(0, min(len(items) - visible, state.index - visible // 2))
        for row, i in enumerate(range(start, min(len(items), start + visible))):
            item = items[i]
            y = top + row * ITEM_H
            selected = i == state.index
            if selected:
                rect = pygame.Rect(MARGIN - 8, y - 4,
                                   WIDTH - 2 * MARGIN + 16, ITEM_H - 6)
                pygame.draw.rect(canvas, self.theme.selection_bg, rect,
                                 border_radius=6)
            color = self.theme.fg if selected else self.theme.muted
            label = font.render(str(item.get("label", "")), True, color)
            canvas.blit(label, (MARGIN + 6, y + 2))
            sublabel = item.get("sublabel")
            if sublabel:
                surf = detail_font.render(str(sublabel), True,
                                          self.theme.muted)
                canvas.blit(surf, (WIDTH - MARGIN - surf.get_width(),
                                   y + font.get_height() - 20))

    # -- list ------------------------------------------------------------

    def _draw_list(self, canvas, state):
        self._draw_title(canvas, state.screen.get("title"))
        items = state.items
        font = self.theme.font("item")
        detail_font = self.theme.font("detail")
        top = BODY_TOP
        row_h = 56
        visible = max(1, (HEIGHT - top - FOOTER_H - 8) // row_h)
        state.page_size = visible
        start = max(0, min(max(0, len(items) - visible), state.scroll))
        end = min(len(items), start + visible)
        y = top
        for i in range(start, end):
            item = items[i]
            if isinstance(item, dict):
                text = str(item.get("text", ""))
                detail = item.get("detail")
            else:
                text, detail = str(item), None
            canvas.blit(font.render(text, True, self.theme.fg), (MARGIN, y))
            y += font.get_height() + 4
            if detail:
                canvas.blit(detail_font.render(str(detail), True,
                                               self.theme.muted),
                            (MARGIN + 12, y))
                y += detail_font.get_height() + 4
            y += 8
        self._scrollbar(canvas, start, end, len(items))

    def _scrollbar(self, canvas, start, end, total):
        if total <= (end - start):
            return
        track = pygame.Rect(WIDTH - MARGIN + 4, BODY_TOP, 6,
                            HEIGHT - BODY_TOP - FOOTER_H)
        pygame.draw.rect(canvas, self.theme.muted, track, border_radius=3)
        frac = (end - start) / total
        thumb_h = max(20, int(track.height * frac))
        pos = int((track.height - thumb_h) * (start / max(1, total - (end - start))))
        thumb = pygame.Rect(track.x, track.y + pos, track.width, thumb_h)
        pygame.draw.rect(canvas, self.theme.accent, thumb, border_radius=3)

    # -- text ------------------------------------------------------------

    def _draw_text(self, canvas, state):
        self._draw_title(canvas, state.screen.get("title"))
        font = self.theme.font("body")
        lines = wrap_text(font, state.screen.get("body", ""),
                          WIDTH - 2 * MARGIN)
        top = BODY_TOP
        line_h = font.get_linesize()
        visible = max(1, (HEIGHT - top - FOOTER_H - 8) // line_h)
        state.page_size = visible
        start = max(0, min(max(0, len(lines) - visible), state.scroll))
        end = min(len(lines), start + visible)
        for row, i in enumerate(range(start, end)):
            canvas.blit(font.render(lines[i], True, self.theme.fg),
                        (MARGIN, top + row * line_h))
        self._scrollbar(canvas, start, end, len(lines))

    # -- image / slideshow ----------------------------------------------

    def _draw_image(self, canvas, state):
        self._draw_picture(canvas, state.screen.get("image"))
        self._draw_caption(canvas, state.screen.get("caption"))

    def _draw_picture(self, canvas, path):
        surf = self._surface(path)
        if surf is None:
            self.message(canvas, "Missing image: %s" % path)
            return
        rect = surf.get_rect()
        scale = min(WIDTH / rect.width, HEIGHT / rect.height)
        size = (max(1, int(rect.width * scale)),
                max(1, int(rect.height * scale)))
        scaled = pygame.transform.smoothscale(surf, size)
        canvas.blit(scaled, scaled.get_rect(center=(WIDTH // 2, HEIGHT // 2)))

    def _draw_slideshow(self, canvas, state):
        slides = state.items
        if not slides:
            return
        index = min(state.slide_index, len(slides) - 1)
        slide = slides[index]
        self._draw_picture(canvas, slide.get("image"))
        self._draw_caption(canvas, slide.get("caption"))
        total = len(slides)
        if total > 1:
            gap = SLIDE_DOT_R * 4
            total_w = gap * (total - 1)
            x = WIDTH // 2 - total_w // 2
            y = 16
            for i in range(total):
                color = (self.theme.accent if i == index
                         else self.theme.muted)
                pygame.draw.circle(canvas, color, (x + i * gap, y),
                                   SLIDE_DOT_R)

    # -- video -----------------------------------------------------------

    def _draw_video(self, canvas, state):
        self._draw_title(canvas, "Video")
        self.message(canvas, "Playing %s ..." % state.screen.get("video"),
                     y=HEIGHT // 2)

    def video_unavailable(self, canvas, footer=None):
        """Placeholder shown when mpv can't play a video screen (#7)."""
        canvas.fill(self.theme.bg)
        self._draw_title(canvas, "Video unavailable")
        self.message(canvas, "mpv is not installed.\n\nPress A to continue.",
                     y=HEIGHT // 2)
        if footer:
            self._draw_footer(canvas, footer)

    # -- overlays --------------------------------------------------------

    def controls_overlay(self, canvas):
        """First-run key-map overlay drawn over the current screen (#7)."""
        scrim = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        scrim.fill((0, 0, 0, 200))
        canvas.blit(scrim, (0, 0))

        title_font = self.theme.font("subtitle")
        body_font = self.theme.font("detail")
        line_h = body_font.get_linesize()
        title_h = title_font.get_height()
        hint_h = body_font.get_height()
        panel_w = 380
        panel_h = (20 + title_h + 12 + len(CONTROL_HINTS) * line_h
                   + 10 + hint_h + 18)
        panel = pygame.Rect(0, 0, panel_w, panel_h)
        panel.center = (WIDTH // 2, HEIGHT // 2)
        pygame.draw.rect(canvas, self.theme.bg, panel, border_radius=10)
        pygame.draw.rect(canvas, self.theme.accent, panel, width=2,
                         border_radius=10)

        header = title_font.render("Controls", True, self.theme.fg)
        canvas.blit(header, header.get_rect(
            midtop=(WIDTH // 2, panel.top + 18)))
        y = panel.top + 18 + title_h + 12
        for key, action in CONTROL_HINTS:
            canvas.blit(body_font.render(key, True, self.theme.accent),
                        (panel.left + 24, y))
            label = body_font.render(action, True, self.theme.fg)
            canvas.blit(label, (panel.right - 24 - label.get_width(), y))
            y += line_h
        hint = body_font.render("Press any button", True, self.theme.muted)
        canvas.blit(hint, hint.get_rect(
            midbottom=(WIDTH // 2, panel.bottom - 10)))

    # -- fallbacks -------------------------------------------------------

    def _draw_notice(self, canvas, state):
        self.message(canvas, state.screen.get("text", ""))

    def message(self, canvas, text, y=None):
        font = self.theme.font("body")
        lines = wrap_text(font, text, WIDTH - 2 * MARGIN)
        line_h = font.get_linesize()
        total = line_h * len(lines)
        start_y = (HEIGHT - total) // 2 if y is None else y - total // 2
        for i, line in enumerate(lines):
            surf = font.render(line, True, self.theme.fg)
            canvas.blit(surf, surf.get_rect(
                center=(WIDTH // 2, start_y + i * line_h + line_h // 2)))

    def error(self, canvas, errors):
        canvas.fill(self.theme.bg)
        font = self.theme.font("body")
        y = MARGIN
        canvas.blit(self.theme.font("title").render(
            "Invalid package", True, (230, 90, 90)), (MARGIN, y))
        y += 50
        for err in errors[:12]:
            for line in wrap_text(font, "- %s" % err, WIDTH - 2 * MARGIN):
                canvas.blit(font.render(line, True, self.theme.fg),
                            (MARGIN, y))
                y += font.get_linesize()
        self._draw_footer(canvas, "Press FN/Esc to quit")
