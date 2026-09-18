# r36s-disp

Daily content player for the R36S handheld (ArkOS). A server generates a
daily "edition" (menus, lists, images, audio, video), packages it into one
file, and the device syncs and plays it full-screen.

**[SPEC.md](SPEC.md) is the source of truth.** Read it before working on
anything. Implementation issues reference its sections.

Planned layout:

```
app/            device app (Python 3 + pygame) — manifest interpreter
server/         publisher + sync endpoints (FastAPI)
testpackages/   hand-authored test editions (full, minimal, invalid)
tests/          pytest
```

Target device: R36S (RK3326, aarch64, 640×480, ArkOS), launched as an
EmulationStation port from `/roms/ports/daily/`.

## Development (desktop, M2 player)

The player is a manifest interpreter. Pure logic (validation, navigation,
timing, input) has no pygame dependency; pygame is only needed to render.

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt

.venv/bin/pytest                                   # includes pygame smoke tests
.venv/bin/python -m app.main testpackages/full     # play a sample package
```

`app.main` also accepts a `.zip`, `--no-video`, `--window 960x720`, and
`--validate-only`. With no argument it reads the `data/current` pointer file
(written by sync, holding a package id) and resolves `data/packages/<id>`,
falling back to the built-in "No edition yet" notice.

Desktop controls: arrows = D-pad, Z/X = A/B, C/V = X/Y, Q/E = L1/R1,
Enter = Start, Tab = Select, Esc/FN = quit.

## Server (desktop, M3)

Publisher plus the two read-only endpoints from SPEC.md §4.1. The store lives
under `server/store/` (gitignored): `packages/<package_id>.zip` and
`devices/<device_id>.json`.

```sh
uv pip install --python .venv/bin/python -r server/requirements.txt

# Validate a content dir, zip it, and point a device at it. Every run mints a
# new package_id, so re-publishing is an intra-day revision (SPEC.md §4.2).
.venv/bin/python -m server.publish testpackages/full \
    --device r36s-01 --retention-days 7

# Serve it on a configurable host/port.
.venv/bin/uvicorn server.app:app --host 0.0.0.0 --port 8001
```

```sh
curl http://<host>:8001/api/v1/devices/r36s-01/latest
# {"package_id": "...", "date": "...", "url": "...", "sha256": "...", "size": ..., ...}

curl -o edition.zip http://<host>:8001/api/v1/packages/<package_id>.zip
sha256sum edition.zip   # must match "sha256" from latest
```

Unknown device → `204`. `X-Device-Token` is accepted and ignored (reserved).

### Device sync client (SPEC.md §4.2)

`app.sync` is the device half: it fetches `latest`, downloads and verifies the
package, validates it, and atomically repoints `data/current`. It is stdlib
only and never raises — failures land in `data/state.json`.

```sh
# config.json: {server_url, device_id, max_retention_days}
.venv/bin/python -m app.sync path/to/config.json --data-dir path/to/data
```

`data_dir` defaults to `data/` next to the config. `max_retention_days`
(default 7) caps whatever retention the server advertises; pruning is by
package `date` and never removes `current`.

## Device deploy (R36S, M4)

Verified on ArkOS (RK3326, Ubuntu 19.10, Python 3.7.5), 2026-09-12. See
also `../r36s/DEPLOYMENT.md` and `../r36s/BOOTSTRAP.md`.

```sh
# One-time setup, then every code/config change:
./deploy/deploy.sh --host <ip> --install    # setup: pygame + mpv + SDL2 KMSDRM shim
./deploy/deploy.sh --host <ip>              # app/ + testpackages/full + launcher
./deploy/deploy.sh --find                   # ARP-scan for the device when its
                                            # DHCP IP changed (or R36S_HOST=<ip>)
```

Launcher: `/roms/ports/daily.sh` (ES Ports entry) runs
`python3 -m app.main` from `/roms/ports/daily/` on KMSDRM. The R36S has no
keyboard, so the player reads the GO-Super Gamepad directly via pygame
(button indices in `app/player/input.py` `JOYMAP`). Press **FN** (joystick
button 16) to exit back to EmulationStation (the launcher restarts ES, since
our KMSDRM app takes DRM master from it).

Device quirks found in M4:
- pygame's bundled SDL2 2.28.4 lacks the KMSDRM video driver; `install.sh`
  repoints it at the system SDL2 (2.30), which has it. No X11 on ArkOS.
- The R36S FN/hotkey is joystick button **16** (ES reports `system_hk` as
  15); `gptokeyb`/`oga_controls` don't see it, so input is read natively.
- `/roms` is exfat with `symlink=0`, so a symlink can't represent the
  installed edition. `data/current` is instead a text file holding the
  `package_id`; `app.current` resolves it to `data/packages/<id>` and swaps it
  with an atomic `os.replace` (#10).
- ArkOS boots without an RTC; fix the clock before apt/pip (TLS).
