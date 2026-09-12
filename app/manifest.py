"""Load a validated package (directory or zip) into memory.

Per SPEC.md §3, a package is either a directory or a zip with the same
layout. Callers are expected to run :func:`app.validate.validate_package`
first; this module assumes a valid package and raises :class:`PackageError`
on IO/parse failures instead of validating.
"""

import json
import os
import zipfile

from typing import Dict, Optional

MANIFEST_NAME = "manifest.json"


class PackageError(Exception):
    """Raised when a package cannot be read or parsed."""


class LoadedPackage:
    """An in-memory package: parsed manifest plus raw asset bytes."""

    def __init__(self, manifest, assets, source=None):
        # type: (dict, Dict[str, bytes], Optional[str]) -> None
        self.manifest = manifest
        self.assets = assets
        self.source = source

    @property
    def root(self):
        # type: () -> str
        return self.manifest.get("root", "")

    @property
    def screens(self):
        # type: () -> dict
        return self.manifest.get("screens", {})

    @property
    def package(self):
        # type: () -> dict
        return self.manifest.get("package", {})

    @property
    def package_id(self):
        # type: () -> str
        return str(self.package.get("id", ""))

    @property
    def title(self):
        # type: () -> str
        return str(self.package.get("title", ""))

    def asset(self, path):
        # type: (str) -> bytes
        try:
            return self.assets[path]
        except KeyError:
            raise PackageError("asset not in package: %s" % path)

    @classmethod
    def from_screens(cls, screens, root, package=None, assets=None):
        """Build an in-memory package (used for the built-in placeholder)."""
        manifest = {
            "spec": 1,
            "package": package or {"id": "builtin", "title": "No edition"},
            "root": root,
            "screens": screens,
        }
        return cls(manifest, assets or {}, source=None)


def _normalize(path):
    return path.replace("\\", "/")


def _load_dir(path):
    manifest = None
    assets = {}  # type: Dict[str, bytes]
    for dirpath, _dirnames, filenames in os.walk(path):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = _normalize(os.path.relpath(full, path))
            try:
                with open(full, "rb") as fh:
                    data = fh.read()
            except OSError as exc:
                raise PackageError("cannot read %s: %s" % (rel, exc))
            if rel == MANIFEST_NAME:
                manifest = data
            else:
                assets[rel] = data
    return manifest, assets


def _load_zip(path):
    manifest = None
    assets = {}  # type: Dict[str, bytes]
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackageError("not a readable zip: %s" % exc)
    with zf:
        for info in zf.infolist():
            name = _normalize(info.filename)
            if name.endswith("/"):
                continue
            try:
                data = zf.read(info.filename)
            except (KeyError, RuntimeError) as exc:
                raise PackageError("cannot read %s: %s" % (name, exc))
            if name == MANIFEST_NAME:
                manifest = data
            else:
                assets[name] = data
    return manifest, assets


def load_package(path):
    # type: (str) -> LoadedPackage
    """Load a package directory or zip.

    Raises :class:`PackageError` if the path is missing, unreadable, or has
    no parseable manifest.
    """
    path = os.fspath(path)
    if not os.path.exists(path):
        raise PackageError("package not found: %s" % path)

    if os.path.isdir(path):
        manifest, assets = _load_dir(path)
    else:
        manifest, assets = _load_zip(path)

    if manifest is None:
        raise PackageError("manifest.json not found in %s" % path)
    try:
        data = json.loads(manifest.decode("utf-8"))
    except UnicodeDecodeError:
        raise PackageError("manifest.json is not valid UTF-8")
    except json.JSONDecodeError as exc:
        raise PackageError("manifest.json is not valid JSON: %s" % exc)
    if not isinstance(data, dict):
        raise PackageError("manifest.json must be a JSON object")

    return LoadedPackage(data, assets, source=path)
