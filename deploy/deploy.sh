#!/bin/bash
# Deploy the daily player to the R36S (ArkOS) at /roms/ports/daily.
#
#   deploy/deploy.sh --host <ip>            # app + fixtures + launcher
#   deploy/deploy.sh --find                 # ARP-scan for the device IP
#   deploy/deploy.sh --host <ip> --install  # plus one-time setup
#
# The device gets a fresh DHCP address each boot and its r8188eus WiFi is
# flaky, so --host / R36S_HOST is required unless you use --find. SSH is
# non-interactive: a dead link fails fast instead of hanging for a password
# prompt (root key auth only, see ../r36s/BOOTSTRAP.md).
#
# Never touches /roms/ports/daily/data, so installed editions survive.
set -euo pipefail

GAMEDIR=/roms/ports/daily
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WLAN_MAC="${R36S_WLAN_MAC:-00:e0:5c:06:45:54}"

HOST="${R36S_HOST:-}"
INSTALL=0
APP=1
TESTPKGS=1

usage() {
  cat <<'EOF'
usage: deploy.sh [--host IP] [--find] [--install] [--app-only]
                 [--no-testpackages]

  --host IP            device IP, or set R36S_HOST. New DHCP IP each boot,
                       so this is usually required.
  --find               ARP-scan the LAN for the device's WiFi MAC
                       (override with R36S_WLAN_MAC).
  --install            also run the one-time deploy/install.sh setup.
  --app-only           skip testpackages/full fixtures.
  --no-testpackages    skip testpackages/full fixtures.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --find) FIND=1; shift ;;
    --install) INSTALL=1; shift ;;
    --app-only) TESTPKGS=0; shift ;;
    --no-testpackages) TESTPKGS=0; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

find_device_ip() {
  local gw pat
  gw="$(ip -4 route show default 2>/dev/null | awk '{print $3; exit}')"
  [ -n "$gw" ] || return 1
  pat="$(printf '%s' "$WLAN_MAC" | tr 'A-F' 'a-f')"
  ip neigh flush all >/dev/null 2>&1 || true
  for i in $(seq 1 254); do
    ping -c1 -W1 -i0.05 "${gw%.*}.$i" >/dev/null 2>&1 &
  done
  wait || true
  ip neigh show | awk -v pat="$pat" '$4 == pat {print $1; exit}'
}

if [ "${FIND:-0}" = 1 ]; then
  HOST="$(find_device_ip)" || true
  [ -n "$HOST" ] || { echo "no device on LAN with MAC $WLAN_MAC" >&2; exit 1; }
  echo "device: $HOST"
elif [ -z "$HOST" ]; then
  echo "no device: pass --host <ip> or set R36S_HOST (or use --find)" >&2
  exit 2
fi

SSH() {
  ssh -o LogLevel=ERROR -o BatchMode=yes -o ConnectTimeout=8 root@"$HOST" "$@"
}

if ! SSH true; then
  echo "no SSH to root@$HOST — the r8188eus WiFi is flaky; reboot the device " \
       "(rc.local auto-reconnects) and re-run" >&2
  exit 1
fi

if [ "$INSTALL" = 1 ]; then
  echo "== one-time device setup (deploy/install.sh) =="
  scp -o LogLevel=ERROR -o BatchMode=yes \
      "$ROOT"/deploy/install.sh root@"$HOST":/tmp/daily-install.sh
  SSH "bash /tmp/daily-install.sh"
  SSH "rm -f /tmp/daily-install.sh"
fi

if [ "$APP" = 1 ]; then
  echo "== app code -> $GAMEDIR/app =="
  tar -C "$ROOT" --exclude='__pycache__' -czf - app |
    SSH "rm -rf $GAMEDIR/app && mkdir -p $GAMEDIR/app && \
         tar --no-same-owner -xzf - -C $GAMEDIR"
fi

if [ "$TESTPKGS" = 1 ]; then
  echo "== testpackages/full -> $GAMEDIR/testpackages/full =="
  tar -C "$ROOT/testpackages" -czf - full |
    SSH "rm -rf $GAMEDIR/testpackages/full && \
         mkdir -p $GAMEDIR/testpackages && \
         tar --no-same-owner -xzf - -C $GAMEDIR/testpackages"
fi

echo "== config.json + daily.sh =="
scp -o LogLevel=ERROR -o BatchMode=yes \
    "$ROOT"/deploy/config.json "$ROOT"/deploy/daily.sh root@"$HOST":$GAMEDIR/
SSH "chmod +x $GAMEDIR/daily.sh"

echo "== verify =="
PYCHECK="import app, app.player, app.sync; print('import ok')"
SSH "cd $GAMEDIR && python3 -c \"$PYCHECK\""

echo "deploy complete: $HOST"