"""Device sync client (SPEC.md §4.2). Stdlib only, Python 3.8+.

Downloads the edition the server points this device at, verifies it, validates
it, and atomically swaps ``data/current`` to the new install. Every failure is
non-fatal: the previous ``current`` is left intact, the error is recorded in
``data/state.json``, and a status dict is returned — :func:`sync` never raises.

Importable API:

    from app.sync import sync
    state = sync("config.json", "data")

CLI:

    python -m app.sync <config.json> [--data-dir <dir>]

Config is JSON: ``{server_url, device_id, max_retention_days}``. ``max_retention_days``
defaults to 7 and caps whatever the server advertises (SPEC.md §4.2). An
optional ``token`` is sent as the reserved ``X-Device-Token`` header (§4.1).
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from typing import Optional

from app.current import packages_dir, read_current, write_current
from app.validate import validate_package

STATE_NAME = "state.json"
INCOMING_NAME = "incoming"
STAGING_PREFIX = ".staging-"
TMP_SUFFIX = ".zip.tmp"

DEFAULT_MAX_RETENTION_DAYS = 7
DEFAULT_TIMEOUT = 20

STATUS_INSTALLED = "installed"
STATUS_UP_TO_DATE = "up-to-date"
STATUS_NO_PACKAGE = "no-package"
STATUS_ERROR = "error"

_SYMLINK_MODE = 0o120000


class SyncError(Exception):
    """A recoverable sync failure; recorded in state.json, never raised out."""


def _is_safe_rel_path(path):
    if not isinstance(path, str) or not path:
        return False
    norm = path.replace("\\", "/")
    if norm.startswith("/") or ":" in norm.split("/")[0]:
        return False
    parts = norm.split("/")
    return "" not in parts and ".." not in parts


def _parse_date(value):
    # type: (object) -> Optional[datetime.date]
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return datetime.datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _utcnow():
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


def _load_config(path):
    with open(path, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    if not isinstance(config, dict):
        raise SyncError("config must be a JSON object")
    for key in ("server_url", "device_id"):
        value = config.get(key)
        if not isinstance(value, str) or not value:
            raise SyncError("config is missing %r" % key)
    cap = config.get("max_retention_days", DEFAULT_MAX_RETENTION_DAYS)
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
        raise SyncError("max_retention_days must be a non-negative integer")
    return config


def _write_state(data_dir, state):
    try:
        os.makedirs(data_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=data_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2, sort_keys=True)
                fh.write("\n")
            os.replace(tmp, os.path.join(data_dir, STATE_NAME))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError:
        pass


class _Deadline:
    """Hard wall-clock budget for the whole sync, applied per socket op."""

    def __init__(self, timeout):
        self.timeout = timeout
        self.start = time.monotonic()

    def remaining(self):
        left = self.timeout - (time.monotonic() - self.start)
        if left <= 0:
            raise SyncError("sync timed out after %gs" % self.timeout)
        return left


def _headers(config):
    token = config.get("token")
    return {"X-Device-Token": token} if token else {}


def _open(url, config, deadline):
    request = urllib.request.Request(url, headers=_headers(config))
    return urllib.request.urlopen(request, timeout=deadline.remaining())


def _fetch_latest(config, deadline):
    base = config["server_url"].rstrip("/")
    device = urllib.parse.quote(config["device_id"], safe="")
    url = "%s/api/v1/devices/%s/latest" % (base, device)
    with _open(url, config, deadline) as resp:
        body = resp.read()
    if getattr(resp, "status", resp.getcode()) == 204 or not body:
        return None
    try:
        record = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SyncError("bad latest response: %s" % exc)
    if not isinstance(record, dict) or not record.get("package_id"):
        raise SyncError("latest response has no package_id")
    return record


def _download(record, config, dest, deadline):
    base = config["server_url"].rstrip("/") + "/"
    url = urllib.parse.urljoin(base, record.get("url", ""))
    digest = hashlib.sha256()
    size = 0
    try:
        with _open(url, config, deadline) as resp, open(dest, "wb") as out:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                deadline.remaining()
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
    except urllib.error.HTTPError as exc:
        raise SyncError("download failed: HTTP %s" % exc.code)
    except urllib.error.URLError as exc:
        raise SyncError("download failed: %s" % exc.reason)
    return digest.hexdigest(), size


def _verify(record, sha256, size):
    expected_sha = record.get("sha256")
    if expected_sha and sha256 != expected_sha:
        raise SyncError("sha256 mismatch: expected %s, got %s" %
                        (expected_sha, sha256))
    expected_size = record.get("size")
    if expected_size is not None and size != expected_size:
        raise SyncError("size mismatch: expected %s, got %d" %
                        (expected_size, size))


def _extract(zip_path, dest):
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            if (info.external_attr >> 16) & 0o170000 == _SYMLINK_MODE:
                raise SyncError("symlink not allowed in package: %s" % name)
            if not _is_safe_rel_path(name):
                raise SyncError("unsafe path in package: %s" % name)
            target = os.path.join(dest, name.replace("/", os.sep))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _install(staging, target):
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.isdir(target):
        shutil.rmtree(target)
    os.replace(staging, target)


def _effective_retention(config, record):
    cap = config.get("max_retention_days", DEFAULT_MAX_RETENTION_DAYS)
    server_days = record.get("retention_days")
    if isinstance(server_days, bool) or not isinstance(server_days, int):
        return cap
    return min(server_days, cap)


def _installed_packages(data_dir):
    root = packages_dir(data_dir)
    try:
        names = os.listdir(root)
    except OSError:
        return []
    return [n for n in names if os.path.isdir(os.path.join(root, n))]


def _package_date(data_dir, package_id):
    path = os.path.join(packages_dir(data_dir), package_id, "manifest.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        return None
    package = manifest.get("package") if isinstance(manifest, dict) else None
    if not isinstance(package, dict):
        return None
    return _parse_date(package.get("date")) or _parse_date(package.get("generated_at"))


def _prune(data_dir, keep_id, retention_days, reference_date):
    """Delete packages dated before the retention window; never the kept one."""
    removed = []
    cutoff = reference_date - datetime.timedelta(days=retention_days)
    for name in _installed_packages(data_dir):
        if name == keep_id:
            continue
        date = _package_date(data_dir, name)
        if date is None or date >= cutoff:
            continue
        try:
            shutil.rmtree(os.path.join(packages_dir(data_dir), name))
            removed.append(name)
        except OSError:
            pass
    return removed


def _finish(data_dir, state):
    _write_state(data_dir, state)
    return state


def sync(config_path, data_dir=None, timeout=DEFAULT_TIMEOUT):
    """Run one sync within ``timeout`` seconds; always returns a status dict.

    ``data_dir`` defaults to ``data/`` next to ``config_path``. The returned
    (and persisted) dict is ``{last_sync, status, package_id, error?}`` where
    status is one of ``installed``/``up-to-date``/``no-package``/``error``.
    """
    config_path = os.fspath(config_path)
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(config_path)),
                                "data")
    data_dir = os.fspath(data_dir)

    state = {
        "last_sync": _utcnow(),
        "status": STATUS_ERROR,
        "package_id": read_current(data_dir),
    }
    try:
        config = _load_config(config_path)
        deadline = _Deadline(timeout)
        record = _fetch_latest(config, deadline)
        if record is None:
            state["status"] = STATUS_NO_PACKAGE
            return _finish(data_dir, state)

        package_id = record["package_id"]
        state["package_id"] = package_id
        reference_date = (_parse_date(record.get("date"))
                          or datetime.date.today())
        retention = _effective_retention(config, record)

        if package_id == read_current(data_dir):
            state["status"] = STATUS_UP_TO_DATE
            _prune(data_dir, package_id, retention, reference_date)
            return _finish(data_dir, state)

        _install_package(config, data_dir, record, deadline)
        state["status"] = STATUS_INSTALLED
        _prune(data_dir, package_id, retention, reference_date)
    except SyncError as exc:
        state["status"] = STATUS_ERROR
        state["error"] = str(exc)
    except Exception as exc:  # never let a sync failure escape
        state["status"] = STATUS_ERROR
        state["error"] = "%s: %s" % (type(exc).__name__, exc)
    return _finish(data_dir, state)


def _install_package(config, data_dir, record, deadline):
    package_id = record["package_id"]
    incoming = os.path.join(data_dir, INCOMING_NAME)
    os.makedirs(incoming, exist_ok=True)
    tmp = os.path.join(incoming, package_id + TMP_SUFFIX)
    staging = None
    installed = False
    try:
        sha256, size = _download(record, config, tmp, deadline)
        _verify(record, sha256, size)
        staging = tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=incoming)
        _extract(tmp, staging)
        errors = validate_package(staging)
        if errors:
            raise SyncError("invalid package: %s" % "; ".join(errors))
        _install(staging, os.path.join(packages_dir(data_dir), package_id))
        installed = True
        write_current(data_dir, package_id)
    finally:
        if staging and not installed:
            shutil.rmtree(staging, ignore_errors=True)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m app.sync",
        description="Sync the device to the server's latest package.",
    )
    parser.add_argument("config", help="path to config.json")
    parser.add_argument("--data-dir", default=None,
                        help="device data dir (default: data/ next to config)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="hard timeout in seconds (default: %(default)s)")
    args = parser.parse_args(argv)

    state = sync(args.config, args.data_dir, args.timeout)
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0 if state["status"] != STATUS_ERROR else 1


if __name__ == "__main__":
    sys.exit(main())
