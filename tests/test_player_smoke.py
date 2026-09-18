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


def test_video_unavailable_waits_for_a(canvas):
    package = load_package(FULL)
    player = Player(package, no_video=True)
    player._canvas = canvas
    player.running = True
    player._enter("video")
    player._step(0.016)
    assert player._video_blocked is True
    assert player.state.sid == "video"
    player._dispatch("a")
    assert player._video_blocked is False
    assert player.state.sid == "menu"


def test_video_available_plays_and_advances(canvas):
    package = load_package(FULL)
    player = Player(package, no_video=False)
    played = []
    player.video._which = lambda name: "/usr/bin/mpv"
    player.video._runner = lambda argv: played.append(argv) or 0
    player.running = True
    player._enter("video")
    player._step(0.016)
    assert played
    assert player._video_blocked is False
    assert player.state.sid == "menu"


def test_main_runs_startup_sync_before_loading(monkeypatch, tmp_path):
    import app.main as main_mod
    import app.player.app as player_mod

    order = []
    booted = LoadedPackage.from_screens(
        {"notice": {"type": "notice", "text": "booted"}}, "notice",
        package={"id": "booted", "title": "Booted"})
    monkeypatch.setattr(main_mod, "startup_sync",
                        lambda cb: order.append("sync") or "synced booted")
    monkeypatch.setattr(main_mod, "load_current",
                        lambda data_dir: order.append("load") or booted)

    captured = {}

    class FakePlayer:
        def __init__(self, package, **kwargs):
            captured["package"] = package
            captured["status"] = kwargs.get("status")

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(player_mod, "Player", FakePlayer)

    assert main_mod.main(["--data-dir", str(tmp_path)]) == 0
    assert order == ["sync", "load"]
    assert captured["package"] is booted
    assert captured["status"] == "synced booted"
    assert captured.get("ran") is True


def test_main_explicit_package_skips_startup_sync(monkeypatch, tmp_path):
    import app.main as main_mod
    import app.player.app as player_mod

    order = []
    monkeypatch.setattr(main_mod, "startup_sync",
                        lambda cb: order.append("sync") or "synced")

    class FakePlayer:
        def __init__(self, package, **kwargs):
            self.package = package

        def run(self):
            order.append("run")

    monkeypatch.setattr(player_mod, "Player", FakePlayer)

    assert main_mod.main([FULL, "--data-dir", str(tmp_path)]) == 0
    assert order == ["run"]


def test_sync_reloads_newly_installed_package(canvas):
    package = load_package(FULL)
    new_package = LoadedPackage.from_screens(
        {"start": {"type": "notice", "text": "new edition"}}, "start",
        package={"id": "full-0002", "title": "New edition"})
    player = Player(package, no_video=True,
                    sync_callback=lambda: "synced full-0002",
                    reload_callback=lambda: new_package)
    player._canvas = canvas
    old_renderer = player.renderer
    player._enter("menu")

    player._do_sync()

    assert player.status == "synced full-0002"
    assert player.package is new_package
    assert player.renderer is not old_renderer
    assert player.stack.root == "start"
    assert player.state.sid == "start"


def test_sync_keeps_package_when_unchanged(canvas):
    package = load_package(FULL)
    player = Player(package, no_video=True,
                    sync_callback=lambda: "already up to date",
                    reload_callback=lambda: load_package(FULL))
    player._canvas = canvas
    player._enter("menu")

    player._do_sync()

    assert player.package is package
    assert player.state.sid == "menu"


def test_sync_survives_reload_failure(canvas):
    package = load_package(FULL)

    def boom():
        raise RuntimeError("disk gone")

    player = Player(package, no_video=True,
                    sync_callback=lambda: "synced full-0002",
                    reload_callback=boom)
    player._canvas = canvas
    player._enter("menu")

    player._do_sync()

    assert player.package is package
    assert player.state.sid == "menu"


def test_controls_overlay_dismissed_by_input(canvas):
    package = load_package(FULL)
    marked = []
    player = Player(package, show_controls=True,
                    controls_callback=lambda: marked.append(True))
    player._canvas = canvas
    player._enter("intro")
    assert player._overlay == "controls"
    player._dispatch("up")
    assert player._overlay is None
    assert player.state.sid == "intro"
    assert marked == [True]


def test_render_overlays(canvas):
    package = load_package(FULL)
    renderer = Renderer(package, Theme())
    renderer.controls_overlay(canvas)
    renderer.video_unavailable(canvas, footer="test")
