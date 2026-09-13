"""CLI publisher for the package server (SPEC.md §4, §7).

Validates a content directory, zips it to ``<store>/packages/<package_id>.zip``
and points one or more devices at it. Package identity is ``package_id``, not
``date`` (SPEC.md §4.2), so every run mints a fresh id — re-publishing the same
content is an intra-day revision.

    python -m server.publish <content-dir> --device <id> [--retention-days N]
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import zipfile

from app.validate import validate_package

from server import DEFAULT_STORE

DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PublishError(Exception):
    """Raised when a package cannot be validated or published."""


def _read_manifest(content_dir):
    path = os.path.join(content_dir, "manifest.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        raise PublishError("cannot read manifest.json: %s" % exc)
    if not isinstance(manifest, dict):
        raise PublishError("manifest.json must be a JSON object")
    return manifest


def _base_name(manifest):
    pkg = manifest.get("package")
    pkg = pkg if isinstance(pkg, dict) else {}
    raw = pkg.get("id") or pkg.get("title") or "daily"
    slug = re.sub(r"[^a-z0-9]+", "-", str(raw).lower()).strip("-")
    return re.sub(r"-\d+$", "", slug) or "daily"


def _package_date(manifest):
    pkg = manifest.get("package")
    pkg = pkg if isinstance(pkg, dict) else {}
    date = pkg.get("date")
    if isinstance(date, str) and DATE_RE.match(date):
        return date
    generated = pkg.get("generated_at")
    if isinstance(generated, str) and DATE_RE.match(generated[:10]):
        return generated[:10]
    return datetime.date.today().isoformat()


def _next_package_id(packages_dir, base, date):
    prefix = "%s-%s-" % (base, date)
    seq = 1
    while os.path.exists(os.path.join(packages_dir, "%s%04d.zip" % (prefix, seq))):
        seq += 1
    return "%s%04d" % (prefix, seq)


def _zip_dir(src, dst):
    entries = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames.sort()
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src).replace(os.sep, "/")
            entries.append((rel, full))
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, full in sorted(entries):
            zf.write(full, rel)


def _sha256_and_size(path):
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _write_record(devices_dir, device_id, record):
    path = os.path.join(devices_dir, device_id + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def publish_package(content_dir, device_ids, store_dir=None, retention_days=None):
    """Validate, zip, and publish ``content_dir`` to one or more devices.

    ``device_ids`` is a device id or an iterable of them. Returns the latest
    record written for each device. Raises :class:`PublishError` (leaving the
    store untouched) if the package is invalid.
    """
    content_dir = os.fspath(content_dir)
    if isinstance(device_ids, str):
        device_ids = [device_ids]
    device_ids = list(device_ids)
    if not device_ids:
        raise PublishError("at least one device id is required")
    for device_id in device_ids:
        if not DEVICE_ID_RE.match(device_id) or ".." in device_id:
            raise PublishError("invalid device id: %r" % device_id)

    errors = validate_package(content_dir)
    if errors:
        raise PublishError("invalid package: %s" % "; ".join(errors))

    manifest = _read_manifest(content_dir)
    store_dir = os.fspath(store_dir or DEFAULT_STORE)
    packages_dir = os.path.join(store_dir, "packages")
    devices_dir = os.path.join(store_dir, "devices")
    os.makedirs(packages_dir, exist_ok=True)
    os.makedirs(devices_dir, exist_ok=True)

    package_id = _next_package_id(packages_dir, _base_name(manifest),
                                  _package_date(manifest))
    _zip_dir(content_dir, os.path.join(packages_dir, package_id + ".zip"))
    sha256, size = _sha256_and_size(os.path.join(packages_dir, package_id + ".zip"))

    record = {
        "package_id": package_id,
        "date": _package_date(manifest),
        "url": "/api/v1/packages/%s.zip" % package_id,
        "sha256": sha256,
        "size": size,
    }
    if retention_days is not None:
        record["retention_days"] = retention_days

    for device_id in device_ids:
        _write_record(devices_dir, device_id, record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m server.publish",
        description="Validate and publish a content directory to a device.",
    )
    parser.add_argument("content_dir", help="directory containing manifest.json")
    parser.add_argument("--device", action="append", required=True,
                        metavar="ID", help="target device id (repeatable)")
    parser.add_argument("--retention-days", type=int, default=None,
                        help="value served in latest.retention_days")
    parser.add_argument("--store", default=DEFAULT_STORE,
                        help="store directory (default: %(default)s)")
    args = parser.parse_args(argv)

    try:
        record = publish_package(args.content_dir, args.device, args.store,
                                 args.retention_days)
    except PublishError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("published %s" % record["package_id"])
    print("sha256 %s size %d" % (record["sha256"], record["size"]))
    for device_id in args.device:
        print("device %s -> %s" % (device_id, record["url"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
