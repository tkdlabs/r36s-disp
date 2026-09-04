"""Manifest/package validator per SPEC.md §3.5.

Stdlib only, Python 3.8+.

Importable API:

    from app.validate import validate_package
    errors = validate_package("path/to/package.zip")  # list[str], [] == valid

CLI:

    python -m app.validate <package-dir-or-zip>
    # exit 0 + "OK", or exit 1 + one error per line
"""

import json
import os
import re
import sys
import zipfile

from typing import Dict, List

# --- Spec constants -----------------------------------------------------

SPEC_VERSION = 1

SCREEN_ID_RE = re.compile(r"^[a-z0-9_-]{1,32}$")

SCREEN_TYPES = ("menu", "list", "image", "video", "text", "slideshow")

BUTTONS = ("up", "down", "left", "right", "a", "b", "x", "y",
           "l1", "l2", "r1", "r2", "start", "select", "fn")

INPUT_ACTIONS = ("back", "home", "sync", "next", "exit")

TRANSITIONS = ("fade", "cut")

IMAGE_EXTS = (".jpg", ".png")
AUDIO_EXTS = (".mp3",)
VIDEO_EXTS = (".mp4",)

# §3.5 rule 4 / §3.1 limits.
MAX_SCREENS = 64
MAX_ITEMS = 200
MAX_BODY_LEN = 10000
MAX_CAPTION_LEN = 500

# §3.5 rule 3 — default 64 MB total (§3.1); per-asset capped at the total.
MAX_TOTAL_SIZE = 64 * 1024 * 1024
MAX_ASSET_SIZE = 64 * 1024 * 1024

_SYMLINK_MODE = 0o120000


# --- path helpers -------------------------------------------------------

def _is_safe_rel_path(path):
    """Reject absolute paths, `..` components, empty/odd components."""
    if not isinstance(path, str) or not path:
        return False
    norm = path.replace("\\", "/")
    if norm.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", norm):
        return False
    parts = norm.split("/")
    if "" in parts or ".." in parts:
        return False
    return True


# --- package collection -------------------------------------------------

def _collect_zip(path, errors):
    files = {}          # type: Dict[str, int]
    manifest = None     # type: bytes | None
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        return files, manifest, ["not a readable zip: %s" % exc]

    with zf:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            mode = (info.external_attr >> 16) & 0o170000
            if mode == _SYMLINK_MODE:
                errors.append("symlink not allowed: %s" % name)
                continue
            if not _is_safe_rel_path(name):
                errors.append("unsafe path in package: %s" % name)
                continue
            if name in files:
                errors.append("duplicate entry: %s" % name)
                continue
            files[name] = info.file_size
            if name == "manifest.json":
                try:
                    manifest = zf.read(name)
                except (KeyError, RuntimeError) as exc:
                    errors.append("cannot read manifest.json: %s" % exc)
    return files, manifest, errors


def _collect_dir(root, errors):
    files = {}          # type: Dict[str, int]
    manifest = None     # type: bytes | None
    for dirpath, dirnames, filenames in os.walk(root):
        for dn in dirnames:
            full = os.path.join(dirpath, dn)
            if os.path.islink(full):
                errors.append("symlink not allowed: %s" %
                              os.path.relpath(full, root).replace(os.sep, "/"))
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.islink(full):
                errors.append("symlink not allowed: %s" % rel)
                continue
            if not _is_safe_rel_path(rel):
                errors.append("unsafe path in package: %s" % rel)
                continue
            files[rel] = os.path.getsize(full)
            if rel == "manifest.json":
                with open(full, "rb") as fh:
                    manifest = fh.read()
    return files, manifest, errors


# --- manifest validation -------------------------------------------------

def _check_screen_ref(value, screens, err):
    if not isinstance(value, str):
        err("reference must be a string, got %r" % (value,))
        return
    if value not in screens:
        err("dangling reference to screen %r" % value)


def _check_asset(value, exts, files, err):
    if not isinstance(value, str):
        err("asset path must be a string, got %r" % (value,))
        return
    if not _is_safe_rel_path(value):
        err("unsafe asset path: %r" % value)
        return
    if value not in files:
        err("missing asset: %r" % value)
        return
    ext = os.path.splitext(value)[1].lower()
    if ext not in exts:
        err("asset %r has extension %r (expected one of %s)" %
            (value, ext, ", ".join(exts)))
    if files[value] > MAX_ASSET_SIZE:
        err("asset %r exceeds %d-byte size limit" % (value, MAX_ASSET_SIZE))


def _check_len(value, limit, what, err):
    if not isinstance(value, str):
        err("%s must be a string, got %r" % (what, type(value).__name__))
        return
    if len(value) > limit:
        err("%s length %d exceeds %d" % (what, len(value), limit))


def _check_items(scr, kind, screens, err, menu=False):
    items = scr.get("items")
    if not isinstance(items, list):
        err("%s screen requires an 'items' list" % kind)
        return
    if len(items) > MAX_ITEMS:
        err("%s has %d items (max %d)" % (kind, len(items), MAX_ITEMS))
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            err("%s item %d must be an object" % (kind, i))
            continue
        if menu:
            if not isinstance(item.get("label"), str):
                err("menu item %d missing string 'label'" % i)
            has_goto = "goto" in item
            has_action = "action" in item
            if has_goto == has_action:
                err("menu item %d must have exactly one of 'goto' or 'action'" % i)
            if has_goto:
                _check_screen_ref(item["goto"], screens, err)
            if has_action and item["action"] not in INPUT_ACTIONS:
                err("menu item %d has invalid action %r" % (i, item["action"]))
        else:
            if not isinstance(item.get("text"), str):
                err("list item %d missing string 'text'" % i)


def _check_inputs(inputs, screens, err):
    if not isinstance(inputs, dict):
        err("'inputs' must be an object")
        return
    for btn, val in inputs.items():
        if btn not in BUTTONS:
            err("unknown button %r" % btn)
        if not isinstance(val, str):
            err("value for button %r must be a string" % btn)
            continue
        if val not in INPUT_ACTIONS:
            _check_screen_ref(val, screens, err)


def _check_screen(sid, scr, screens, files, errors):
    def err(msg):
        errors.append("screen %r: %s" % (sid, msg))

    if not isinstance(scr, dict):
        err("screen must be an object")
        return

    stype = scr.get("type")
    if stype not in SCREEN_TYPES:
        err("unknown or missing screen type %r" % (stype,))
        return

    if "transition" in scr and scr["transition"] not in TRANSITIONS:
        err("invalid transition %r (expected 'fade' or 'cut')" % scr["transition"])

    if "duration" in scr and (isinstance(scr["duration"], bool)
                              or not isinstance(scr["duration"], (int, float))):
        err("'duration' must be a number")

    if "audio" in scr:
        _check_asset(scr["audio"], AUDIO_EXTS, files, err)

    if "audio_loop" in scr and not isinstance(scr["audio_loop"], bool):
        err("'audio_loop' must be a boolean")

    if "next" in scr:
        _check_screen_ref(scr["next"], screens, err)

    if "inputs" in scr:
        _check_inputs(scr["inputs"], screens, err)

    if stype == "menu":
        _check_items(scr, "menu", screens, err, menu=True)
    elif stype == "list":
        _check_items(scr, "list", screens, err)
    elif stype == "image":
        if scr.get("image") is None:
            err("image screen missing 'image'")
        else:
            _check_asset(scr["image"], IMAGE_EXTS, files, err)
        if "caption" in scr:
            _check_len(scr["caption"], MAX_CAPTION_LEN, "caption", err)
    elif stype == "video":
        if scr.get("video") is None:
            err("video screen missing 'video'")
        else:
            _check_asset(scr["video"], VIDEO_EXTS, files, err)
    elif stype == "text":
        if scr.get("body") is None:
            err("text screen missing 'body'")
        else:
            _check_len(scr["body"], MAX_BODY_LEN, "body", err)
    elif stype == "slideshow":
        slides = scr.get("slides")
        if not isinstance(slides, list) or not slides:
            err("slideshow requires a non-empty 'slides' list")
            return
        for i, sl in enumerate(slides):
            if not isinstance(sl, dict):
                err("slide %d must be an object" % i)
                continue
            if sl.get("image") is None:
                err("slide %d missing 'image'" % i)
            else:
                _check_asset(sl["image"], IMAGE_EXTS, files, err)
            if "caption" in sl:
                _check_len(sl["caption"], MAX_CAPTION_LEN,
                           "slide %d caption" % i, err)
            if "duration" in sl and (isinstance(sl["duration"], bool)
                                     or not isinstance(sl["duration"], (int, float))):
                err("slide %d 'duration' must be a number" % i)


def _validate_manifest(manifest, files, errors):
    if manifest is None:
        errors.append("manifest.json not found")
        return
    try:
        data = json.loads(manifest.decode("utf-8"))
    except UnicodeDecodeError:
        errors.append("manifest.json is not valid UTF-8")
        return
    except json.JSONDecodeError as exc:
        errors.append("manifest.json is not valid JSON: %s" % exc)
        return
    if not isinstance(data, dict):
        errors.append("manifest must be a JSON object")
        return

    spec = data.get("spec")
    if spec != SPEC_VERSION:
        errors.append("unsupported spec %r (expected %d)" % (spec, SPEC_VERSION))

    screens = data.get("screens")
    if not isinstance(screens, dict):
        errors.append("'screens' must be an object")
        return

    if len(screens) > MAX_SCREENS:
        errors.append("screen count %d exceeds %d" % (len(screens), MAX_SCREENS))

    for sid in screens:
        if not isinstance(sid, str) or not SCREEN_ID_RE.match(sid):
            errors.append("invalid screen id %r" % (sid,))

    root = data.get("root")
    if not isinstance(root, str):
        errors.append("'root' is missing or not a string")
    elif root not in screens:
        errors.append("root screen %r does not exist" % root)

    for sid, scr in screens.items():
        _check_screen(sid, scr, screens, files, errors)

    total = sum(files.values())
    if total > MAX_TOTAL_SIZE:
        errors.append("package size %d exceeds %d bytes" % (total, MAX_TOTAL_SIZE))


# --- public API ----------------------------------------------------------

def validate_package(path) -> List[str]:
    """Validate a package directory or zip. Returns list of error strings.

    An empty list means the package is valid.
    """
    path = os.fspath(path)
    if not os.path.exists(path):
        return ["package not found: %s" % path]

    errors = []  # type: List[str]
    if os.path.isdir(path):
        files, manifest, errors = _collect_dir(path, errors)
    else:
        files, manifest, errors = _collect_zip(path, errors)

    _validate_manifest(manifest, files, errors)
    return errors


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m app.validate <package-dir-or-zip>",
              file=sys.stderr)
        return 2
    errors = validate_package(argv[0])
    if errors:
        for e in errors:
            print(e)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
