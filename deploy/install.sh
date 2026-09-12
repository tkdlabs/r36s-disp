#!/bin/bash
# One-time device setup for the daily player on ArkOS / R36S.
# Run as root on the device (see ../r36s/DEPLOYMENT.md, ../r36s/BOOTSTRAP.md).
#
# NOTE: the device clock must be correct or apt/pip TLS fails; ArkOS boots
# without an RTC. If needed: date -u -s "$(date -u +%F\ %T)" or NTP.
set -e

export DEBIAN_FRONTEND=noninteractive

echo "[1/3] apt packages: python3-pip, mpv"
apt-get install -y python3-pip mpv

echo "[2/3] pygame 2.6.1 (cp37 aarch64 wheel)"
python3 -m pip install --upgrade "pip==24.0"
python3 -m pip install "pygame==2.6.1"

echo "[3/3] SDL2 KMSDRM shim"
# pygame ships SDL2 2.28.4 built without the KMSDRM video driver, which ArkOS
# needs (no X11). Repoint the bundled library at the system SDL2, which has it.
SYS_SDL=$(ls -1 /usr/lib/aarch64-linux-gnu/libSDL2-2.0.so.0.* | sort -V | tail -1)
PYGAME_LIBS=$(python3 -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")/pygame.libs
for lib in "$PYGAME_LIBS"/libSDL2-2-*.so.*; do
  case "$lib" in
    *.bundled) continue ;;
  esac
  [ -e "$lib.bundled" ] || cp -a "$lib" "$lib.bundled"
  ln -sf "$SYS_SDL" "$lib"
  echo "  $(basename "$lib") -> $SYS_SDL"
done

echo "done. Deploy app files to /roms/ports/daily/ and launch via /roms/ports/daily.sh"
