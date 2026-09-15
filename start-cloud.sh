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
pulseaudio --system --daemonize=yes --disallow-exit --exit-idle-time=-1 --load="module-native-protocol-unix socket=/tmp/pulse/native auth-anonymous=1" --load="module-null-sink sink_name=takarada sink_properties=device.description=Takarada" >/tmp/pulse.log 2>&1 || true
export PULSE_SERVER=unix:/tmp/pulse/native
pactl set-default-sink takarada >/dev/null 2>&1 || true
pactl set-default-source takarada.monitor >/dev/null 2>&1 || true
node bootstrap.js &
NODE_PID=$!
node renderer.js &
RENDERER_PID=$!
trap 'kill "$RENDERER_PID" "$NODE_PID" "$XVFB_PID" 2>/dev/null || true' TERM INT EXIT
wait "$NODE_PID"
