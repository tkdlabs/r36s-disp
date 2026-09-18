from app.manifest import LoadedPackage
from app.player.input import button_for_joy, button_for_key, direction_for_axis
from app.player.screens import Action, ScreenState


def pkg(screens, root):
    return LoadedPackage.from_screens(screens, root)


def test_image_duration_auto_advances():
    package = pkg({
        "intro": {"type": "image", "image": "a.jpg", "duration": 2,
                  "next": "menu"},
        "menu": {"type": "menu", "items": []},
    }, "intro")
    state = ScreenState(package, "intro")
    assert state.tick(1.0) is None
    assert state.tick(1.0) == Action("next", "menu")


def test_image_without_duration_waits():
    package = pkg({"intro": {"type": "image", "image": "a.jpg"}}, "intro")
    state = ScreenState(package, "intro")
    assert state.tick(100.0) is None
    assert state.resolve("a") == Action("next", None)


def test_slideshow_timing():
    package = pkg({
        "show": {
            "type": "slideshow",
            "slides": [
                {"image": "s1.jpg", "duration": 3},
                {"image": "s2.jpg", "duration": 3},
            ],
            "next": "home",
        },
        "home": {"type": "menu", "items": []},
    }, "show")
    state = ScreenState(package, "show")
    assert state.tick(2.0) is None
    assert state.slide_index == 0
    assert state.tick(1.1) is None
    assert state.slide_index == 1
    assert state.tick(3.0) == Action("next", "home")


def test_list_scroll_clamps():
    package = pkg({
        "list": {"type": "list", "items": [
            {"text": "one"}, {"text": "two"}, {"text": "three"}]},
    }, "list")
    state = ScreenState(package, "list", page_size=2)
    state.resolve("down")
    state.resolve("down")
    state.resolve("down")
    assert state.scroll == 2
    state.resolve("up")
    state.resolve("up")
    state.resolve("up")
    assert state.scroll == 0


def test_list_page_moves_by_page_size():
    items = [{"text": str(i)} for i in range(10)]
    package = pkg({"list": {"type": "list", "items": items}}, "list")
    state = ScreenState(package, "list", page_size=4)
    state.resolve("right")
    assert state.scroll == 4
    state.resolve("l1")
    assert state.scroll == 0


def test_menu_select_goto():
    package = pkg({
        "menu": {"type": "menu", "items": [
            {"label": "Agenda", "goto": "agenda"},
            {"label": "Quit", "action": "exit"},
        ]},
        "agenda": {"type": "list", "items": []},
    }, "menu")
    state = ScreenState(package, "menu")
    assert state.resolve("a") == Action("goto", "agenda")
    state.resolve("down")
    assert state.resolve("a") == Action("exit")


def test_menu_selection_clamps():
    package = pkg({"menu": {"type": "menu", "items": [
        {"label": "a", "goto": "menu"}]}}, "menu")
    state = ScreenState(package, "menu")
    state.resolve("up")
    assert state.index == 0
    state.resolve("down")
    assert state.index == 0


def test_inputs_override():
    package = pkg({"screen": {"type": "image", "image": "a.jpg",
                              "inputs": {"a": "back", "y": "home"}}}, "screen")
    state = ScreenState(package, "screen")
    assert state.resolve("a") == Action("back")
    assert state.resolve("y") == Action("home")


def test_inputs_override_to_screen():
    package = pkg({
        "screen": {"type": "list", "items": [], "inputs": {"x": "menu"}},
        "menu": {"type": "menu", "items": []},
    }, "screen")
    state = ScreenState(package, "screen")
    assert state.resolve("x") == Action("goto", "menu")


def test_default_back_sync_exit():
    package = pkg({"screen": {"type": "image", "image": "a.jpg"}}, "screen")
    state = ScreenState(package, "screen")
    assert state.resolve("b") == Action("back")
    assert state.resolve("select") == Action("sync")
    assert state.resolve("fn") == Action("exit")


def test_start_home_for_read_media_advances():
    read = pkg({"menu": {"type": "menu", "items": []}}, "menu")
    assert ScreenState(read, "menu").resolve("start") == Action("home")

    media = pkg({"img": {"type": "image", "image": "a.jpg",
                         "next": "img"}}, "img")
    assert ScreenState(media, "img").resolve("start") == Action("next", "img")


def test_button_for_key():
    assert button_for_key("Up") == "up"
    assert button_for_key("z") == "a"
    assert button_for_key("RETURN") == "start"
    assert button_for_key("right shift") == "select"
    assert button_for_key("tab") == "select"
    assert button_for_key("f1") is None
    assert button_for_key(None) is None


def test_button_for_joy_r36s_map():
    assert button_for_joy(0) == "b"
    assert button_for_joy(1) == "a"
    assert button_for_joy(8) == "up"
    assert button_for_joy(12) == "select"
    assert button_for_joy(13) == "start"
    assert button_for_joy(16) == "fn"
    assert button_for_joy(15) is None


def test_direction_for_axis():
    assert direction_for_axis(1, -1.0) == "up"
    assert direction_for_axis(1, 1.0) == "down"
    assert direction_for_axis(0, -1.0) == "left"
    assert direction_for_axis(0, 1.0) == "right"
    assert direction_for_axis(1, 0.1) is None
    assert direction_for_axis(3, 1.0) is None
