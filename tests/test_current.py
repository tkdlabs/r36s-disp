import os
import shutil

import pytest

from app.current import (
    current_pointer,
    packages_dir,
    read_current,
    resolve_current,
    write_current,
)
from app.main import load_current, make_reload_callback, resolve_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FULL = os.path.join(ROOT, "testpackages", "full")


def _install(data_dir, package_id):
    path = os.path.join(packages_dir(data_dir), package_id)
    os.makedirs(path)
    return path


def test_read_missing_returns_none(tmp_path):
    assert read_current(str(tmp_path)) is None


def test_read_malformed_returns_none(tmp_path):
    with open(current_pointer(str(tmp_path)), "w") as fh:
        fh.write("../escape\n")
    assert read_current(str(tmp_path)) is None


def test_roundtrip(tmp_path):
    write_current(str(tmp_path), "full-0001")
    assert read_current(str(tmp_path)) == "full-0001"


def test_write_is_a_regular_file_not_symlink(tmp_path):
    write_current(str(tmp_path), "full-0001")
    assert os.path.isfile(current_pointer(str(tmp_path)))
    assert not os.path.islink(current_pointer(str(tmp_path)))


def test_write_replaces_previous_pointer(tmp_path):
    write_current(str(tmp_path), "a-1")
    write_current(str(tmp_path), "b-2")
    assert read_current(str(tmp_path)) == "b-2"


def test_write_leaves_no_temp_files(tmp_path):
    write_current(str(tmp_path), "full-0001")
    leftovers = [n for n in os.listdir(str(tmp_path)) if ".tmp" in n]
    assert leftovers == []


@pytest.mark.parametrize("bad", ["", None, "../x", "a/b", "x" * 129])
def test_write_rejects_invalid_ids(tmp_path, bad):
    with pytest.raises(ValueError):
        write_current(str(tmp_path), bad)


def test_resolve_installed(tmp_path):
    path = _install(str(tmp_path), "full-0001")
    write_current(str(tmp_path), "full-0001")
    assert resolve_current(str(tmp_path)) == path


def test_resolve_dangling_returns_none(tmp_path):
    write_current(str(tmp_path), "gone-0001")
    assert resolve_current(str(tmp_path)) is None


def test_resolve_missing_returns_none(tmp_path):
    _install(str(tmp_path), "full-0001")
    assert resolve_current(str(tmp_path)) is None


def test_resolve_ignores_directory_in_pointer_slot(tmp_path):
    os.makedirs(current_pointer(str(tmp_path)))
    assert read_current(str(tmp_path)) is None
    assert resolve_current(str(tmp_path)) is None


def test_write_migrates_stale_directory_in_pointer_slot(tmp_path):
    stale = current_pointer(str(tmp_path))
    os.makedirs(os.path.join(stale, "assets"))
    with open(os.path.join(stale, "manifest.json"), "w") as fh:
        fh.write("{}")

    write_current(str(tmp_path), "full-0001")

    assert read_current(str(tmp_path)) == "full-0001"
    assert os.path.isfile(current_pointer(str(tmp_path)))
    parked = [n for n in os.listdir(str(tmp_path))
              if n.startswith("current.stale-")]
    assert len(parked) == 1
    assert os.path.isfile(
        os.path.join(str(tmp_path), parked[0], "manifest.json"))


def test_resolve_path_prefers_explicit(tmp_path):
    assert resolve_path("/some/explicit", str(tmp_path)) == "/some/explicit"


def test_resolve_path_uses_pointer(tmp_path):
    path = _install(str(tmp_path), "full-0001")
    write_current(str(tmp_path), "full-0001")
    assert resolve_path(None, str(tmp_path)) == path


def test_resolve_path_none_when_no_pointer(tmp_path):
    assert resolve_path(None, str(tmp_path)) is None


def test_load_current_none_falls_back_to_builtin(tmp_path):
    package = load_current(str(tmp_path))
    assert package.package_id == "builtin"
    assert "notice" in package.screens


def test_load_current_loads_installed_pointer(tmp_path):
    data_dir = str(tmp_path)
    shutil.copytree(FULL, os.path.join(packages_dir(data_dir), "full-0001"))
    write_current(data_dir, "full-0001")
    assert load_current(data_dir).package_id == "full-0001"


def test_reload_callback_reads_pointer(tmp_path):
    data_dir = str(tmp_path)
    reload = make_reload_callback(data_dir)
    assert reload().package_id == "builtin"

    shutil.copytree(FULL, os.path.join(packages_dir(data_dir), "full-0001"))
    write_current(data_dir, "full-0001")
    assert reload().package_id == "full-0001"
