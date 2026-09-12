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
`--validate-only`. With no argument it looks for `data/current`, and falls
back to the built-in "No edition yet" notice.

Desktop controls: arrows = D-pad, Z/X = A/B, C/V = X/Y, Q/E = L1/R1,
Enter = Start, Tab = Select, Esc/FN = quit.

## Device deploy (R36S, M4)

Verified on ArkOS (RK3326, Ubuntu 19.10, Python 3.7.5), 2026-09-12. See
also `../r36s/DEPLOYMENT.md` and `../r36s/BOOTSTRAP.md`.

```sh
# On the device (as root), once:
bash deploy/install.sh            # pip install pygame==2.6.1 + mpv + SDL2 KMSDRM shim

# From the dev machine:
tar czf - -C . app | ssh root@<ip> 'rm -rf /roms/ports/daily/app && tar xzf - -C /roms/ports/daily/'
tar czf - -C testpackages full | ssh root@<ip> 'mkdir -p /roms/ports/daily/testpackages && tar xzf - -C /roms/ports/daily/testpackages/'
scp deploy/config.json deploy/daily.sh root@<ip>:/roms/ports/daily/
ssh root@<ip> 'chmod +x /roms/ports/daily.sh'
```

Launcher: `/roms/ports/daily.sh` (ES Ports entry) runs
`python3 -m app.main` from `/roms/ports/daily/` on KMSDRM. The R36S has no
keyboard, so the player reads the GO-Super Gamepad directly via pygame
(button indices in `app/player/input.py` `JOYMAP`). Press **FN** (joystick
button 16) to exit back to EmulationStation.

Device quirks found in M4:
- pygame's bundled SDL2 2.28.4 lacks the KMSDRM video driver; `install.sh`
  repoints it at the system SDL2 (2.30), which has it. No X11 on ArkOS.
- The R36S FN/hotkey is joystick button **16** (ES reports `system_hk` as
  15); `gptokeyb`/`oga_controls` don't see it, so input is read natively.
- `/roms` is exfat with `symlink=0`, so the spec's `data/current` symlink
  can't be used; M4 uses `data/current/` as a real directory (#10).
- ArkOS boots without an RTC; fix the clock before apt/pip (TLS).
