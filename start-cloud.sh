#!/usr/bin/env bash
set -e
mkdir -p /tmp/pulse /tmp/pulse-home
export HOME=/tmp/pulse-home
Xvfb :99 -screen 0 ${STREAM_WIDTH:-720}x${STREAM_HEIGHT:-1280}x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
pulseaudio --system --daemonize=yes --disallow-exit --exit-idle-time=-1 --load="module-native-protocol-unix socket=/tmp/pulse/native auth-anonymous=1" --load="module-null-sink sink_name=takarada sink_properties=device.description=Takarada" >/tmp/pulse.log 2>&1 || true
export PULSE_SERVER=unix:/tmp/pulse/native
pactl set-default-sink takarada >/dev/null 2>&1 || true
pactl set-default-source takarada.monitor >/dev/null 2>&1 || true
node server.js &
NODE_PID=$!
sleep 2
CHROME="$(find /ms-playwright -type f -path '*/chrome-linux/chrome' -o -path '*/chrome-linux64/chrome' 2>/dev/null | head -n1)"
if [ -z "$CHROME" ]; then CHROME="$(find /ms-playwright -type f -name chrome 2>/dev/null | head -n1)"; fi
if [ -n "$CHROME" ]; then "$CHROME" --no-sandbox --disable-dev-shm-usage --disable-gpu --autoplay-policy=no-user-gesture-required --window-position=0,0 --window-size=${STREAM_WIDTH:-720},${STREAM_HEIGHT:-1280} --kiosk "http://127.0.0.1:${PORT:-10000}/stage" >/tmp/chrome.log 2>&1 & fi
wait "$NODE_PID"
