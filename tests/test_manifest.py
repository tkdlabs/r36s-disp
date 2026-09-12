import os
import zipfile

import pytest

from app.manifest import LoadedPackage, PackageError, load_package

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTPKG = os.path.join(ROOT, "testpackages")


def test_load_full_dir():
    pkg = load_package(os.path.join(TESTPKG, "full"))
    assert pkg.package_id == "full-0001"
    assert pkg.root == "intro"
    assert "menu" in pkg.screens
    assert pkg.assets["assets/intro.jpg"]
    assert pkg.asset("assets/intro.jpg") == pkg.assets["assets/intro.jpg"]


def test_load_full_zip(tmp_path):
    zip_path = os.path.join(str(tmp_path), "full.zip")
    src = os.path.join(TESTPKG, "full")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, filenames in os.walk(src):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, src).replace(os.sep, "/")
                zf.write(full, rel)

    pkg = load_package(zip_path)
    assert pkg.package_id == "full-0001"
    assert pkg.asset("assets/intro.jpg")


def test_missing_package():
    with pytest.raises(PackageError):
        load_package(os.path.join(TESTPKG, "does-not-exist"))


def test_missing_asset_raises():
    pkg = load_package(os.path.join(TESTPKG, "minimal"))
    with pytest.raises(PackageError):
        pkg.asset("assets/nope.jpg")


def test_builtin_package():
    pkg = LoadedPackage.from_screens(
        {"notice": {"type": "notice", "text": "hi"}}, "notice")
    assert pkg.root == "notice"
    assert pkg.screens["notice"]["text"] == "hi"
    assert pkg.assets == {}
