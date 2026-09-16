#!/usr/bin/env bash
set -euo pipefail
ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-emulator-5554}
(
  for _ in $(seq 1 240); do
    if "$ADB" -s "$SERIAL" shell pm path com.zhiliaoapp.musically >/dev/null 2>&1; then
      sleep 14
      "$ADB" -s "$SERIAL" shell input tap 603 379 >/dev/null 2>&1 || true
      sleep 2
      "$ADB" -s "$SERIAL" shell input tap 603 379 >/dev/null 2>&1 || true
      exit 0
    fi
    sleep 3
  done
) &
exec bash virtual-phone/github-phone-agent-v2.sh
