#!/usr/bin/env bash
set -euo pipefail

export HOME=/tmp/rubyclips-home
export DISPLAY=:99
mkdir -p "$HOME" /tmp/.X11-unix /tmp/youtube-browser /tmp/rubyclips-source
rm -f /tmp/.X99-lock

Xvfb :99 -screen 0 ${STREAM_WIDTH:-720}x${STREAM_HEIGHT:-1280}x24 -ac +extension RANDR -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
for i in $(seq 1 60); do
  if DISPLAY=:99 xdotool getdisplaygeometry >/dev/null 2>&1; then break; fi
  if ! kill -0 "$XVFB_PID" 2>/dev/null; then cat /tmp/xvfb.log >&2; exit 1; fi
  sleep 0.2
done
DISPLAY=:99 xdotool getdisplaygeometry >/dev/null 2>&1 || { cat /tmp/xvfb.log >&2; exit 1; }

node server.js >/tmp/server.log 2>&1 &
SERVER_PID=$!

TARGET_URL="${YOUTUBE_SOURCE_URL:-https://www.youtube.com/watch?v=5-bO9NAhWbI}"
echo "Starting Rubaradaclips YouTube phone for $TARGET_URL"
google-chrome \
  --no-sandbox \
  --disable-dev-shm-usage \
  --disable-gpu \
  --disable-software-rasterizer=false \
  --no-first-run \
  --no-default-browser-check \
  --disable-features=TranslateUI \
  --password-store=basic \
  --window-size=${STREAM_WIDTH:-720},${STREAM_HEIGHT:-1280} \
  --window-position=0,0 \
  --user-data-dir=/tmp/youtube-browser \
  "$TARGET_URL" >/tmp/chrome.log 2>&1 &
CHROME_PID=$!

(
  while true; do
    ffmpeg -hide_banner -loglevel error \
      -f x11grab -video_size ${STREAM_WIDTH:-720}x${STREAM_HEIGHT:-1280} -i :99.0 \
      -frames:v 1 -q:v 4 -y /tmp/cloud-frame-next.jpg >/dev/null 2>&1 || true
    mv -f /tmp/cloud-frame-next.jpg /tmp/cloud-frame.jpg 2>/dev/null || true
    sleep 0.8
  done
) &
CAPTURE_PID=$!

node youtube-worker.js >/tmp/youtube-worker.log 2>&1 &
WORKER_PID=$!

trap 'kill "$WORKER_PID" "$CAPTURE_PID" "$CHROME_PID" "$SERVER_PID" "$XVFB_PID" 2>/dev/null || true' TERM INT EXIT
wait "$SERVER_PID"
