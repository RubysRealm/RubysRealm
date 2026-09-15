#!/usr/bin/env bash
set -e
mkdir -p /tmp/pulse /tmp/pulse-home
export HOME=/tmp/pulse-home
Xvfb :99 -screen 0 ${STREAM_WIDTH:-720}x${STREAM_HEIGHT:-1280}x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
pulseaudio --system --daemonize=yes --disallow-exit --exit-idle-time=-1 --load="module-native-protocol-unix socket=/tmp/pulse/native auth-anonymous=1" --load="module-null-sink sink_name=takarada sink_properties=device.description=Takarada" >/tmp/pulse.log 2>&1 || true
export PULSE_SERVER=unix:/tmp/pulse/native
pactl set-default-sink takarada >/dev/null 2>&1 || true
pactl set-default-source takarada.monitor >/dev/null 2>&1 || true
node bootstrap.js &
NODE_PID=$!
node renderer.js &
RENDERER_PID=$!
trap 'kill "$RENDERER_PID" "$NODE_PID" 2>/dev/null || true' TERM INT EXIT
wait "$NODE_PID"
