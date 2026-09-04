import os
import zipfile

import pytest

from app.validate import validate_package

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTPKG = os.path.join(ROOT, "testpackages")

# Each invalid variant must break exactly one §3.5 rule; map the directory
# name to the fragment its error message must contain.
EXPECTED_RULE = {
    "dangling-goto": "dangling reference",
    "missing-asset": "missing asset",
    "oversized-item-list": "items",
    "path-escape": "unsafe asset path",
    "spec-2": "unsupported spec",
    "wrong-extension": "extension",
}


def _zip_dir(src, dst):
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirnames, filenames in os.walk(src):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, src).replace(os.sep, "/")
                zf.write(full, rel)


def test_full_valid():
    assert validate_package(os.path.join(TESTPKG, "full")) == []


def test_minimal_valid():
    assert validate_package(os.path.join(TESTPKG, "minimal")) == []


def test_full_zip_valid(tmp_path):
    zip_path = os.path.join(str(tmp_path), "full.zip")
    _zip_dir(os.path.join(TESTPKG, "full"), zip_path)
    assert validate_package(zip_path) == []


@pytest.mark.parametrize(
    "variant",
    sorted(os.listdir(os.path.join(TESTPKG, "invalid"))),
)
def test_invalid_variants(variant):
    path = os.path.join(TESTPKG, "invalid", variant)
    errors = validate_package(path)
    assert errors, "expected %r to be invalid" % variant
    assert len(errors) == 1, "expected exactly one violation in %r, got %r" % (
        variant, errors,
    )
    assert EXPECTED_RULE[variant] in errors[0], (
        "error for %r must identify the right rule: %r" % (variant, errors[0])
    )
