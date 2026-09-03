# r36s-disp — Daily Content Player

Spec v0.1 (draft for review)

A semi-interactive player of pre-made content for the R36S (ArkOS). Content is
generated server-side (LLM/agent), packaged into one immutable file per day,
pulled by the device over the LAN (static server IP), and played full-screen.

## 1. Goals / non-goals

Goals:
- Play a daily "edition": intro, menus, lists, images, audio, video.
- Declarative content: the device interprets a manifest; it never executes content.
- Offline-first: device is fully functional from installed packages; sync is best-effort.
- Launchable from EmulationStation as a port; kiosk mode (replace ES) possible later.

Non-goals (v1):
- Live/streamed content, arbitrary web rendering, on-device content generation.
- Uplink/telemetry implementation (schema reserved, see §6).

## 2. Target device facts (from ../r36s docs)

- RK3326, 4× Cortex-A35, 1 GB RAM, aarch64, ArkOS (Ubuntu-based), SDL2 stack.
- Screen: 640×480, 4:3, landscape. Panel variants exist → app must query the
  actual mode at runtime; server assets target 640×480.
- Inputs: D-pad, A/B/X/Y, L1/L2/R1/R2, Start/Select/FN, analog sticks (ADC).
- Audio: mono speaker (+ headphone out). WiFi dongle can cause speaker crackle
  → do network work at startup, not during media playback.
- Deploy path: `/roms/ports/<app>/` + `.sh` launcher (see ../r36s/DEPLOYMENT.md).

## 3. Package format

### 3.1 Container

- One file per edition: `<package_id>.zip` (deflate). ZIP for stdlib support
  on-device (Python `zipfile`) and trivial server side.
- Max recommended size: 64 MB (video dominates; flaky WiFi dongle).
- Layout:

```
manifest.json
assets/
  intro.jpg
  agenda_tts.mp3
  surprise.mp4
  ...
```

- All asset paths are relative, `/`-separated, must stay inside the package
  (no `..`, no absolute paths, no symlinks). UTF-8 everywhere.

### 3.2 manifest.json

Top level:

```json
{
  "spec": 1,
  "package": {
    "id": "daily-2026-09-03",
    "date": "2026-09-03",
    "generated_at": "2026-09-03T06:00:00Z",
    "title": "Thursday, 3 September"
  },
  "root": "intro",
  "theme": { },
  "screens": { "<screen_id>": { } }
}
```

- `spec`: integer, currently `1`. Device refuses packages with `spec` it does
  not support (forward-compat gate).
- `package.id`: unique string; used for install dir + dedupe.
- `theme`: optional in v1; device falls back to built-in dark theme. Reserved
  keys: `bg`, `fg`, `accent`, `font_scale`.

Screen IDs: `[a-z0-9_-]{1,32}`.

### 3.3 Screen types

Common optional fields on every screen:

| field | meaning |
|---|---|
| `audio` | asset path, background audio started on entry, stopped on exit |
| `audio_loop` | bool, default false |
| `duration` | seconds, then auto-advance via `next` |
| `next` | screen id for auto-advance (after `duration`, or video/slideshow end) |
| `inputs` | button overrides, see §3.4 |
| `transition` | `"fade"` (default) or `"cut"` |

#### `menu` — root/navigation hub

```json
{
  "type": "menu",
  "title": "Good morning, Tom",
  "subtitle": "Thursday, 3 September",
  "items": [
    {"label": "Today's agenda",  "sublabel": "4 events", "goto": "agenda"},
    {"label": "Email digest",    "goto": "emails"},
    {"label": "On this day",     "goto": "photo"},
    {"label": "Something nice",  "goto": "surprise"}
  ]
}
```

Item fields: `label` (required), `sublabel` (optional), and exactly one of:
`goto` (screen id) or `action` (`"sync"`, `"exit"`, `"home"`).

#### `list` — read-only scrollable content (agenda, email digest, …)

```json
{
  "type": "list",
  "title": "Today",
  "items": [
    {"text": "09:00  Standup", "detail": "Meet, 15 min"},
    {"text": "13:00  Dentist"}
  ],
  "audio": "assets/agenda_tts.mp3"
}
```

Item fields: `text` (required), `detail` (optional, dimmer/smaller).
D-pad scrolls, L/R page. B back.

#### `image` — full-screen still

```json
{
  "type": "image",
  "image": "assets/2019-09-03.jpg",
  "caption": "You, on this day in 2019",
  "duration": 10,
  "next": "home"
}
```

`caption` optional (bottom bar, semi-transparent). Without `duration`,
A advances (`next` or back).

#### `video`

```json
{
  "type": "video",
  "video": "assets/surprise.mp4",
  "next": "home"
}
```

Played by the system video player (mpv) full-screen; any key ends playback
and returns to the app. On end without input: go to `next` if set, else back.

#### `text` — long-form scrollable

```json
{
  "type": "text",
  "title": "Your day in emails",
  "body": "Line one.\nLine two.\n…"
}
```

#### `slideshow` — timed image sequence with one audio bed

```json
{
  "type": "slideshow",
  "audio": "assets/music.mp3",
  "slides": [
    {"image": "assets/s1.jpg", "caption": "…", "duration": 6},
    {"image": "assets/s2.jpg", "duration": 6}
  ],
  "next": "home"
}
```

### 3.4 Input model

Default bindings (overridable per screen via `inputs: {"<button>": ...}`):

| button | menu/list/text | image/slideshow/video |
|---|---|---|
| D-pad | navigate / scroll | — |
| A | select / advance | advance |
| B | back (nav stack) | back |
| L1/R1 | page up/down | prev/next slide |
| Start | home screen | skip to end/home |
| Select | sync now | sync now |
| FN | quit to EmulationStation | quit to EmulationStation |

`inputs` values: a screen id (goto) or one of `"back"`, `"home"`, `"sync"`,
`"next"`, `"exit"`. Buttons: `up down left right a b x y l1 l2 r1 r2 start
select fn`.

### 3.5 Validation rules (device enforces before install)

1. `manifest.json` parses; `spec == 1`; `root` exists.
2. Every `goto`/`next` target exists; no unreachable-from-root requirement
   (allowed), but no dangling references.
3. Every referenced asset exists in the zip; no path escapes; per-asset and
   total size limits (default: 64 MB total).
4. Screen count ≤ 64; menu/list item count ≤ 200; body/caption length limits.
5. Media files match expected extension per type
   (`.jpg/.png` image, `.mp3` audio, `.mp4` video).

Invalid package → reject, keep last known-good, record error in state file.

### 3.6 Media encoding targets (server-side)

| kind | format |
|---|---|
| image | JPEG q≈85 progressive, **640×480** exact (device does contain/cover fit as fallback); PNG only for graphics needing alpha |
| audio | MP3, 44.1 kHz, **mono**, 96–128 kbps CBR (device speaker is mono) |
| video | MP4, H.264 Main@L4.0, **640×480** (or 480×360 to save bandwidth), 25–30 fps, ~400–900 kbps, AAC-LC mono 96 kbps, `+faststart` |
| speech | generated server-side as TTS → MP3; no on-device TTS |

Video decode baseline is software (mpv/ffmpeg on A35 handles 480p fine);
`--hwdec=auto` lets mpv pick rkvdec where the kernel supports it.

## 4. Sync protocol

Transport: plain HTTP over the LAN. Server address is a **static IP** baked
into device config (no DNS assumptions). Meshnet (NordVPN on the R36S) is a
nice-to-have, deferred (§10).

### 4.1 Endpoints

```
GET /api/v1/devices/{device_id}/latest
→ 200
{
  "package_id": "daily-2026-09-03",
  "date": "2026-09-03",
  "url": "/api/v1/packages/daily-2026-09-03.zip",
  "sha256": "…",
  "size": 1234567,
  "retention_days": 7
}
→ 204 if no package for this device

GET /api/v1/packages/{filename}.zip
→ 200 application/zip
```

Auth v1: none required (private LAN). Reserved: `X-Device-Token` header
pass-through so a token can be added without protocol change.

### 4.2 Device sync flow

1. Read config (`server_url`, `device_id`, `max_retention_days`).
2. `GET latest`; if `package_id` == installed current → done.
3. Download to `data/incoming/<id>.zip.tmp` (resumable not required in v1).
4. Verify sha256 and size → unzip to staging → run §3.5 validation.
5. Atomic switch: move dir to `data/packages/<id>/`, repoint `data/current`
   symlink. Old `current` deleted only after new one validates.
6. Prune packages (never delete `current`).
7. Write `data/state.json`: `{last_sync, status, package_id, error?}` —
   surfaced in UI (e.g. menu footer).

Retention is **server-controlled, device-capped**: the effective retention is
`min(latest.retention_days or ∞, config.max_retention_days)`. The device hard
cap defaults to **7 days** and cannot be raised by the server. Pruning is by
package `date`, keeping the newest within the window plus `current`.

**Intra-day updates** are supported: identity is `package_id`, not `date`, so
a regenerated same-day edition (new `package_id`, same `date`) is picked up on
the next sync. Sync triggers: app start (hard timeout, default 20 s), Select
button (manual/on-demand), optional systemd timer. All failures are non-fatal
to the player.

## 5. Device app

### 5.1 Stack

MVP: **Python 3 + pygame 2 (SDL2)**; video via **mpv** subprocess.
Rationale: fastest path; 1 GB RAM is ample; no compile step for content-side
iteration. The app is a manifest interpreter, so a later C/SDL2 rewrite
(same package format) is possible without server changes.

Dependencies on device: `python3`, `python3-pygame`, `mpv`.

### 5.2 Layout

```
/roms/ports/daily/
  daily.sh              # ES launcher (bash %ROM%)
  config.json           # {server_url, device_id, max_retention_days}
  app/
    main.py             # entry: sync (timeout) → load current → run
    player/             # state machine, screen renderers, input, transitions
    sync.py             # §4 client
    validate.py         # §3.5
    theme.py, fonts/    # built-in dark theme + bundled TTF
  data/
    packages/<package_id>/…
    current -> packages/<id>
    incoming/
    state.json
```

### 5.3 Runtime behavior

- Boot: optional sync → load `current` → `root` screen. No package → built-in
  placeholder screen ("No edition yet — press Select to sync").
- Navigation is a stack; B pops; `home` clears to root.
- Rendering: 640×480 full-screen (query real mode; scale if different).
- Video: stop app audio → `mpv --really-quiet --fullscreen --no-osc <file>` →
  on exit resume app state.
- Audio: one background track at a time; duck/stop on screen exit.
- Quit (FN): clean exit → EmulationStation restarts (standard port behavior).
- Known issue: WiFi dongle can crackle the speaker; sync happens at startup
  and on demand, not during playback.

### 5.4 Kiosk mode (later, optional)

systemd service running `main.py` on boot instead of EmulationStation
(kmsdrm/fbdev). No format changes required; FN/quit becomes "stop service".

## 6. Uplink (reserved, not implemented in v1)

```
POST /api/v1/devices/{device_id}/events
{
  "events": [
    {"ts": "…", "package_id": "…", "type": "installed"},
    {"ts": "…", "package_id": "…", "type": "opened"},
    {"ts": "…", "package_id": "…", "type": "screen_viewed", "payload": {"screen": "agenda"}},
    {"ts": "…", "package_id": "…", "type": "action", "payload": {"screen": "agenda", "button": "a"}}
  ]
}
```

Device side only needs to buffer events to a local file; sending is a
background task with retry. Schema is fixed now so content can start being
logged from day one.

## 7. Server (basic version, post-spec)

- Publisher only: build tool takes a content dir (assets + manifest or
  manifest fragments) → validates → zips → computes sha256 → writes
  `latest` per device. Serving: static files + the two GET endpoints
  (FastAPI or nginx; either is fine, FastAPI preferred for the events stub).
- Test artifacts: 2–3 sample packages — (a) full-feature edition exercising
  every screen type, (b) minimal image+audio intro → menu, (c) deliberately
  invalid package for rejection tests.
- LLM/agent pipeline plugs in later as "the thing that writes the content
  dir"; nothing downstream changes.

## 8. Milestones

- M1: this spec frozen; sample package (a) hand-authored.
- M2: desktop player (pygame) that renders/validates sample packages — develop
  without hardware.
- M3: sync client + server MVP + test artifacts; end-to-end on LAN.
- M4: device deploy per ../r36s/DEPLOYMENT.md; verify video/audio/input.
- M5: hardening — kiosk mode, events uplink, package signing (minisign) if
  the LAN ever stops being trusted.

## 9. Decisions log

1. **Server addressing**: static LAN IP in `config.json`. No discovery.
2. **Retention**: server-controlled via `latest.retention_days`, hard-capped
   on device at 7 days (`max_retention_days`).
3. **Intra-day updates**: allowed; dedupe by `package_id`, picked up on
   manual sync (Select).
4. **Launch mode**: EmulationStation port (kiosk later).
5. **Video**: required in v1 (mpv subprocess).

## 10. Nice-to-haves (deferred)

- Meshnet connectivity: NordVPN (or Tailscale/ZeroTier) on the R36S so sync
  works off-LAN.
- mDNS/discovery instead of static IP.
- Resumable downloads, package signing (minisign), events uplink (§6).
