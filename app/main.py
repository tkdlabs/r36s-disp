"""Entry point: validate -> load a package -> run the player (SPEC.md §5.2).

Usage:

    python -m app.main <package-dir-or-zip> [--no-video] [--window 960x720]
    python -m app.main --config config.json
    python -m app.main --validate-only <package-dir-or-zip>

With no package argument the player resolves the ``data/current`` pointer file
written by sync (§4.2) and otherwise shows the built-in "no edition" notice.
When a sync config exists, the Select button runs the sync client (§4.2) and
reports the outcome in the footer (#21).
"""

import argparse
import os
import sys

from app.current import resolve_current
from app.firstrun import controls_seen, mark_controls_seen
from app.manifest import LoadedPackage, PackageError, load_package
from app.validate import validate_package


def make_sync_callback(config_path=None, data_dir=None):
    """Build the Select-button sync callback, or ``None`` if never configured.

    ``config_path`` defaults to ``config.json`` in the working directory — the
    device launcher cd's to the app dir, so ``python -m app.main`` there just
    works. Returns a zero-arg callable for the player that runs
    :func:`app.sync.sync` and reduces its state dict to a footer string;
    ``None`` keeps the player's "sync unavailable" fallback when no config
    file exists.
    """
    if config_path is None:
        config_path = "config.json"
    if not os.path.isfile(config_path):
        return None

    def _callback():
        from app.sync import sync
        return _sync_summary(sync(config_path, data_dir))

    return _callback


def startup_sync(sync_callback):
    """Run the boot sync once (SPEC.md §4.2); never raises.

    Startup sync is best-effort and offline-first: any failure is reduced to
    the same footer status the Select button shows. ``None`` (no config) keeps
    the footer clean. Returns the status string to seed the player with.
    """
    if sync_callback is None:
        return ""
    try:
        return sync_callback() or ""
    except Exception as exc:  # a sync failure must never block startup
        return "sync failed: %s" % exc


def make_reload_callback(data_dir=None):
    """Build the post-sync reload callback for the player.

    Sync installs a package and repoints ``data/current`` behind the running
    player's back, so after a successful sync the player asks this to load the
    edition now on disk. Returns a zero-arg callable that always yields a
    package, falling back to a built-in notice when ``current`` is missing or
    invalid — mirroring :func:`app.main.main`.
    """
    if data_dir is None:
        data_dir = default_data_dir()

    def _reload():
        return load_current(data_dir)

    return _reload


def load_current(data_dir):
    """Load the package ``data/current`` names, or a built-in notice.

    Uses the same validation/error fallbacks as :func:`main` so a bad install
    surfaces as an on-screen message instead of an exception.
    """
    path = resolve_current(data_dir)
    if path is None:
        return builtin_package("No edition yet - press Select to sync")
    errors = validate_package(path)
    if errors:
        return builtin_package(
            "Cannot play package: %s" % "; ".join(errors[:3]),
            package_id="invalid")
    try:
        return load_package(path)
    except PackageError as exc:
        return builtin_package("Cannot load package: %s" % exc,
                               package_id="error")


def _sync_summary(state):
    """Turn a ``sync()`` state dict into the one-line footer status."""
    status = state.get("status")
    if status == "installed":
        return "synced %s" % state.get("package_id", "")
    if status == "up-to-date":
        return "already up to date"
    if status == "no-package":
        return "nothing to sync"
    return "sync failed: %s" % state.get("error", "unknown error")


def _parse_window(value):
    try:
        w, h = value.lower().split("x", 1)
        return (max(320, int(w)), max(240, int(h)))
    except (ValueError, AttributeError):
        raise argparse.ArgumentTypeError("expected WxH, e.g. 960x720")


def builtin_package(text, package_id="builtin"):
    """A one-screen package used for notices and errors (never validated)."""
    screens = {"notice": {"type": "notice", "text": text}}
    return LoadedPackage.from_screens(
        screens, "notice",
        package={"id": package_id, "title": "r36s-disp"})


def resolve_path(path, data_dir="data"):
    """Return an explicit package path or the package named by data/current."""
    if path:
        return path
    return resolve_current(data_dir)


def default_data_dir(config_path=None):
    """The data dir sync uses: ``data/`` next to the sync config."""
    if config_path is None:
        config_path = "config.json"
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), "data")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="app.main")
    parser.add_argument("package", nargs="?",
                        help="package directory or .zip")
    parser.add_argument("--no-video", action="store_true",
                        help="skip external mpv playback")
    parser.add_argument("--window", type=_parse_window, default=None,
                        help="window size WxH (default 960x720)")
    parser.add_argument("--validate-only", action="store_true",
                        help="validate and exit without opening a window")
    parser.add_argument("--config", default=None,
                        help="sync config.json used by the Select button "
                             "(default: config.json in the working directory)")
    parser.add_argument("--data-dir", default=None,
                        help="sync data dir "
                             "(default: data/ next to --config)")
    args = parser.parse_args(argv)

    if args.package and args.validate_only:
        errors = validate_package(args.package)
        if errors:
            for err in errors:
                print(err, file=sys.stderr)
            return 1
        print("OK")
        return 0

    data_dir = args.data_dir or default_data_dir(args.config)
    sync_callback = make_sync_callback(args.config, data_dir)
    status = ""
    if args.package:
        # Explicit package (desktop/debug): load it strictly, never sync.
        errors = validate_package(args.package)
        if errors:
            for err in errors:
                print(err, file=sys.stderr)
            return 1
        try:
            package = load_package(args.package)
        except PackageError as exc:
            print("cannot load package: %s" % exc, file=sys.stderr)
            return 1
    else:
        # Boot trigger (SPEC.md §4.2): sync before resolving data/current so a
        # stale pointer is refreshed on launch, best-effort and non-blocking.
        status = startup_sync(sync_callback)
        package = load_current(data_dir)

    from app.player.app import Player
    Player(package, window=args.window, no_video=args.no_video,
           sync_callback=sync_callback,
           show_controls=not controls_seen(data_dir),
           controls_callback=lambda: mark_controls_seen(data_dir),
           reload_callback=make_reload_callback(data_dir),
           status=status).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
