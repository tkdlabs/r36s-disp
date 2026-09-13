"""Entry point: validate -> load a package -> run the player (SPEC.md §5.2).

Usage:

    python -m app.main <package-dir-or-zip> [--no-video] [--window 960x720]
    python -m app.main --validate-only <package-dir-or-zip>

With no package argument the player resolves the ``data/current`` pointer file
written by sync (§4.2) and otherwise shows the built-in "no edition" notice.
"""

import argparse
import sys

from app.current import resolve_current
from app.manifest import LoadedPackage, PackageError, load_package
from app.validate import validate_package


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
    args = parser.parse_args(argv)

    if args.package and args.validate_only:
        errors = validate_package(args.package)
        if errors:
            for err in errors:
                print(err, file=sys.stderr)
            return 1
        print("OK")
        return 0

    path = resolve_path(args.package)
    if path is None:
        package = builtin_package("No edition yet - press Select to sync")
    else:
        errors = validate_package(path)
        if errors:
            if args.package:
                for err in errors:
                    print(err, file=sys.stderr)
                return 1
            package = builtin_package(
                "Cannot play package: %s" % "; ".join(errors[:3]),
                package_id="invalid")
        else:
            try:
                package = load_package(path)
            except PackageError as exc:
                if args.package:
                    print("cannot load package: %s" % exc, file=sys.stderr)
                    return 1
                package = builtin_package("Cannot load package: %s" % exc,
                                          package_id="error")

    from app.player.app import Player
    Player(package, window=args.window, no_video=args.no_video).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
