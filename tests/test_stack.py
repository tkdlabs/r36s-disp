from app.player.stack import NavigationStack


def test_starts_at_root():
    s = NavigationStack("root")
    assert s.current == "root"
    assert s.depth == 1


def test_push_and_pop():
    s = NavigationStack("root")
    s.push("a")
    s.push("b")
    assert s.current == "b"
    assert s.depth == 3
    assert s.pop() == "a"
    assert s.current == "a"


def test_pop_at_root_is_safe():
    s = NavigationStack("root")
    assert s.pop() == "root"
    assert s.depth == 1


def test_replace():
    s = NavigationStack("root")
    s.push("a")
    s.replace("b")
    assert s.items() == ["root", "b"]


def test_home_resets_history():
    s = NavigationStack("root")
    s.push("a")
    s.push("b")
    assert s.home() == "root"
    assert s.items() == ["root"]
