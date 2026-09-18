import os

from app.firstrun import controls_seen, mark_controls_seen, marker_path


def test_controls_marker_roundtrip(tmp_path):
    data_dir = str(tmp_path / "data")
    assert controls_seen(data_dir) is False
    mark_controls_seen(data_dir)
    assert controls_seen(data_dir) is True
    assert os.path.isfile(marker_path(data_dir))


def test_mark_controls_seen_swallows_oserror(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    mark_controls_seen(str(blocker / "data"))
    assert controls_seen(str(blocker / "data")) is False
