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

# The R36S has no keyboard; gptokeyb translates the gamepad into the keys
# app/player/input.py expects (see daily.gptk).
GPTOKEYB=/opt/system/Tools/PortMaster/gptokeyb
if [ -x "$GPTOKEYB" ]; then
  chmod 666 /dev/uinput 2>/dev/null
  "$GPTOKEYB" python3 -c "$GAMEDIR/daily.gptk" >> "$GAMEDIR/run.log" 2>&1 &
  GPTOKEYB_PID=$!
fi

python3 -m app.main >> "$GAMEDIR/run.log" 2>&1
STATUS=$?

[ -n "$GPTOKEYB_PID" ] && kill "$GPTOKEYB_PID" 2>/dev/null
exit $STATUS
