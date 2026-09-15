#!/usr/bin/env bash
set -e
mkdir -p /tmp/pulse /tmp/pulse-home /tmp/.X11-unix
export HOME=/tmp/pulse-home
export DISPLAY=:99
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 ${STREAM_WIDTH:-720}x${STREAM_HEIGHT:-1280}x24 -ac +extension RANDR -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!
for i in $(seq 1 50); do
  if DISPLAY=:99 xdotool getdisplaygeometry >/dev/null 2>&1; then break; fi
  if ! kill -0 "$XVFB_PID" 2>/dev/null; then cat /tmp/xvfb.log >&2; exit 1; fi
  sleep 0.2
done
if ! DISPLAY=:99 xdotool getdisplaygeometry >/dev/null 2>&1; then cat /tmp/xvfb.log >&2; exit 1; fi

chown -R pulse:pulse /tmp/pulse /tmp/pulse-home 2>/dev/null || true
pulseaudio --system --daemonize=yes --disallow-exit --exit-idle-time=-1 \
  --load="module-native-protocol-unix socket=/tmp/pulse/native auth-anonymous=1" \
  --load="module-null-sink sink_name=takarada rate=44100 channels=2 sink_properties=device.description=Takarada" \
  >/tmp/pulse.log 2>&1
export PULSE_SERVER=unix:/tmp/pulse/native
PULSE_READY=0
for i in $(seq 1 75); do
  if pactl info >/dev/null 2>&1; then PULSE_READY=1; break; fi
  sleep 0.2
done
if [ "$PULSE_READY" != "1" ]; then
  echo "PulseAudio failed to become ready" >&2
  cat /tmp/pulse.log >&2 || true
  exit 1
fi
pactl set-default-sink takarada
pactl set-default-source takarada.monitor

echo "Cloud audio ready: takarada sink + monitor"
node bootstrap.js &
NODE_PID=$!

if [ "${LOGIN_MODE:-false}" = "true" ]; then
  echo "Starting persistent TikTok cloud login screen"
  mkdir -p /tmp/tiktok-browser
  google-chrome \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --disable-software-rasterizer=false \
    --no-first-run \
    --no-default-browser-check \
    --disable-features=TranslateUI \
    --window-size=${STREAM_WIDTH:-720},${STREAM_HEIGHT:-1280} \
    --window-position=0,0 \
    --user-data-dir=/tmp/tiktok-browser \
    'https://www.tiktok.com/login?lang=en&enter_method=live_studio&enter_from=live_studio' \
    >/tmp/chrome.log 2>&1 &
  CHROME_PID=$!
  (
    while true; do
      ffmpeg -hide_banner -loglevel error -f x11grab -video_size ${STREAM_WIDTH:-720}x${STREAM_HEIGHT:-1280} -i :99.0 -frames:v 1 -q:v 4 -y /tmp/cloud-frame-next.jpg >/dev/null 2>&1 || true
      mv -f /tmp/cloud-frame-next.jpg /tmp/cloud-frame.jpg 2>/dev/null || true
      sleep 0.8
    done
  ) &
  CAPTURE_PID=$!
  trap 'kill "$CAPTURE_PID" "$CHROME_PID" "$NODE_PID" "$XVFB_PID" 2>/dev/null || true' TERM INT EXIT
  wait "$NODE_PID"
  exit 0
fi

node renderer.js &
RENDERER_PID=$!
node tiktok-autolive.js &
AUTOLIVE_PID=$!
trap 'kill "$AUTOLIVE_PID" "$RENDERER_PID" "$NODE_PID" "$XVFB_PID" 2>/dev/null || true' TERM INT EXIT
wait "$NODE_PID"
