#!/usr/bin/env bash
# Regenerate placeholder assets for the test packages.
#
# Uses ffmpeg (lavfi color/testsrc/sine) to produce SPEC §3.6-shaped files:
#   640x480 JPEG images, mono MP3 audio, 640x480 H.264/AAC MP4 (<=5s, +faststart).
#
# Usage: ./testpackages/gen_assets.sh
set -euo pipefail

cd "$(dirname "$0")"

mkdir -p full/assets minimal/assets

FF="ffmpeg -hide_banner -loglevel error -y"

# --- images (640x480 JPEG, q~85) -------------------------------------
$FF -f lavfi -i testsrc=size=640x480:rate=1 -frames:v 1 \
    -pix_fmt yuvj420p -q:v 3 full/assets/intro.jpg
$FF -f lavfi -i "color=c=0x4a7c59:s=640x480" -frames:v 1 \
    -pix_fmt yuvj420p -q:v 3 full/assets/photo.jpg
$FF -f lavfi -i "color=c=0x2e5a88:s=640x480" -frames:v 1 \
    -pix_fmt yuvj420p -q:v 3 full/assets/s1.jpg
$FF -f lavfi -i "color=c=0x8a5a2e:s=640x480" -frames:v 1 \
    -pix_fmt yuvj420p -q:v 3 full/assets/s2.jpg

# --- audio (mono MP3 44.1 kHz) ---------------------------------------
$FF -f lavfi -i "sine=frequency=440:duration=4" \
    -ac 1 -ar 44100 -b:a 96k full/assets/intro.mp3
$FF -f lavfi -i "sine=frequency=330:duration=6" \
    -ac 1 -ar 44100 -b:a 96k full/assets/music.mp3

# --- video (640x480 H.264 Main@L4.0 + AAC mono, +faststart) ----------
$FF -f lavfi -i "testsrc=size=640x480:rate=25:duration=4" \
    -f lavfi -i "sine=frequency=220:duration=4" \
    -c:v libx264 -profile:v main -level 4.0 -pix_fmt yuv420p -b:v 500k \
    -c:a aac -ac 1 -ar 44100 -b:a 96k \
    -movflags +faststart full/assets/video.mp4

# --- minimal package assets ------------------------------------------
cp full/assets/intro.jpg minimal/assets/intro.jpg
cp full/assets/intro.mp3 minimal/assets/intro.mp3

echo "assets generated"
