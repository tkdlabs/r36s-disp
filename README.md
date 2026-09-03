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
