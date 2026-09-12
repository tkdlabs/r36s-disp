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
