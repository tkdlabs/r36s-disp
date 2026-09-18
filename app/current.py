"""Resolve the installed edition without symlinks (SPEC.md §4.2, §5.2).

On the R36S ``/roms`` is exfat mounted with ``symlink=0``, so the spec's
``data/current -> packages/<id>`` symlink cannot exist. Instead ``data/current``
is a small text file holding the installed ``package_id``; readers resolve it
to ``data/packages/<id>``. Swapping the pointer is an atomic
``os.replace`` of a file, so the atomic-switch and never-delete-current
guarantees from §4.2 are preserved.

Stdlib only, Python 3.8+.
"""

import os
import re
import tempfile
import time

CURRENT_NAME = "current"
PACKAGES_NAME = "packages"

PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def packages_dir(data_dir):
    return os.path.join(data_dir, PACKAGES_NAME)


def current_pointer(data_dir):
    return os.path.join(data_dir, CURRENT_NAME)


def read_current(data_dir):
    """Return the installed ``package_id``, or ``None`` if there is none.

    A missing, unreadable, or malformed pointer reads as ``None``.
    """
    try:
        with open(current_pointer(data_dir), "r", encoding="utf-8") as fh:
            package_id = fh.read().strip()
    except OSError:
        return None
    if not PACKAGE_ID_RE.match(package_id):
        return None
    return package_id


def resolve_current(data_dir):
    """Return the directory the pointer names, or ``None`` if it dangles.

    Missing, malformed, or dangling pointers all resolve to ``None`` so callers
    fall back to their "no edition" path.
    """
    package_id = read_current(data_dir)
    if package_id is None:
        return None
    path = os.path.join(packages_dir(data_dir), package_id)
    return path if os.path.isdir(path) else None


def write_current(data_dir, package_id):
    """Atomically point ``data/current`` at ``package_id``.

    Writes a temp file next to the pointer and ``os.replace``s it into place;
    readers never observe a partial pointer and the previous pointer survives
    any failure before the rename.
    """
    if not PACKAGE_ID_RE.match(package_id or ""):
        raise ValueError("invalid package_id: %r" % (package_id,))

    os.makedirs(data_dir, exist_ok=True)
    target = current_pointer(data_dir)
    # Migration (#27): builds before the pointer-file layout kept the installed
    # edition as a directory at ``current``; os.replace can't overwrite one.
    # Park it aside (never delete) so the pointer can be written.
    if os.path.isdir(target):
        backup = target + ".stale-%d" % int(time.time())
        os.rename(target, backup)
    fd, tmp = tempfile.mkstemp(prefix=".current-", suffix=".tmp", dir=data_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(package_id + "\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
