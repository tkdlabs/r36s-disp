#!/bin/bash
# EmulationStation port launcher for the daily content player (SPEC.md §5.2).
# ES invokes this as: bash /roms/ports/daily.sh
GAMEDIR=/roms/ports/daily
cd "$GAMEDIR" || exit 1
export HOME="${HOME:-/home/ark}"

# pygame's bundled SDL2 has no KMSDRM; deploy/install.sh points it at the
# system SDL2, which does. ArkOS runs ES (and ports) on KMS/DRM, no X11.
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-KMSDRM}"
export SDL_VIDEO_KMSDRM_DEVICE="${SDL_VIDEO_KMSDRM_DEVICE:-/dev/dri/card0}"

# Gamepad input is read natively by pygame (see app/player/input.py JOYMAP);
# no gptokeyb keyboard bridge needed.
python3 -m app.main >> "$GAMEDIR/run.log" 2>&1

# Our KMSDRM app takes the DRM master away from ES, which does not repaint
# when we exit (blank screen). Queue an ES restart from systemd (pid 1 does
# the work even though this script is in ES's cgroup and gets torn down).
if systemctl is-active --quiet emulationstation 2>/dev/null; then
  sudo systemctl --no-block restart emulationstation >/dev/null 2>&1
fi
printf '\033c' > /dev/tty1 2>/dev/null
printf '\033c' > /dev/tty0 2>/dev/null
exit 0
