import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

pygame = pytest.importorskip("pygame")

from app.manifest import LoadedPackage, load_package  # noqa: E402
from app.player.app import Player  # noqa: E402
from app.player.render import Renderer  # noqa: E402
from app.player.screens import Action, ScreenState  # noqa: E402
from app.player.theme import Theme  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FULL = os.path.join(ROOT, "testpackages", "full")


@pytest.fixture(scope="module")
def canvas():
    pygame.display.init()
    pygame.display.set_mode((320, 240))
    pygame.font.init()
    surface = pygame.Surface((640, 480))
    yield surface
    pygame.quit()


def test_render_every_screen_type(canvas):
    package = load_package(FULL)
    renderer = Renderer(package, Theme(package.manifest.get("theme")))
    for sid in package.screens:
        state = ScreenState(package, sid)
        renderer.draw(canvas, state, footer="test")


def test_render_notice_and_error(canvas):
    package = LoadedPackage.from_screens(
        {"notice": {"type": "notice", "text": "No edition yet"}}, "notice")
    renderer = Renderer(package, Theme())
    state = ScreenState(package, "notice")
    renderer.draw(canvas, state)
    renderer.error(canvas, ["unsupported spec 2", "missing asset: x"])


def test_player_navigation(canvas):
    package = load_package(FULL)
    player = Player(package, no_video=True)
    player._canvas = canvas
    player._enter("intro")
    assert player.state.sid == "intro"

    player._apply(Action("goto", "menu"))
    assert player.state.sid == "menu"
    assert player.stack.depth == 2

    player._apply(Action("back"))
    assert player.state.sid == "intro"

    player._apply(Action("home"))
    assert player.state.sid == "intro"
    assert player.stack.depth == 1


def test_theme_uses_bundled_font(canvas):
    from app.player import theme as theme_mod
    assert os.path.isfile(theme_mod.FONT_PATH)
    theme = theme_mod.Theme()
    size = max(8, int(theme_mod.BASE_SIZES["body"] * theme.font_scale))
    expected = pygame.font.Font(theme_mod.FONT_PATH, size)
    assert theme.font("body").size("Hello, Wg") == expected.size("Hello, Wg")


def test_theme_falls_back_when_font_missing(canvas, monkeypatch):
    from app.player import theme as theme_mod
    monkeypatch.setattr(theme_mod, "FONT_PATH", "/nonexistent/NotoSans.ttf")
    font = theme_mod.Theme().font("body")
    assert font.render("Hello", True, (255, 255, 255)).get_width() > 0


def test_player_video_screen_is_pending(canvas):
    package = load_package(FULL)
    player = Player(package, no_video=True)
    player._canvas = canvas
    player._enter("video")
    assert player._video_pending is True
