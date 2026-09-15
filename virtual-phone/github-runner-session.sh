#!/usr/bin/env bash
set -euo pipefail

ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-emulator-5554}
FEED_URL=${TAKARADA_FEED_URL:-https://takarada-cloud-live.onrender.com/preview}
ROOT=/tmp/takarada-phone
mkdir -p "$ROOT"

$ADB -s "$SERIAL" wait-for-device
$ADB -s "$SERIAL" shell wm size 720x1280 || true
$ADB -s "$SERIAL" shell wm density 320 || true
$ADB -s "$SERIAL" shell settings put system screen_off_timeout 2147483647 || true
$ADB -s "$SERIAL" shell svc power stayon true || true

# Install the Takarada full-screen feed app from this branch.
$ADB -s "$SERIAL" install -r virtual-phone/prebuilt/takarada-display.apk

# Install Aurora Store so TikTok can be installed from the Google Play catalog
# without requiring us to bundle a third-party TikTok APK.
curl -fL --retry 3 -o "$ROOT/aurora.apk" https://f-droid.org/repo/com.aurora.store_76.apk
$ADB -s "$SERIAL" install -r "$ROOT/aurora.apk" || true

# Start the Takarada feed once so the app is initialized.
$ADB -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "$FEED_URL" || true
sleep 3

# Expose the Android screen in a browser using scrcpy -> Xvfb -> noVNC.
export DISPLAY=:99
Xvfb :99 -screen 0 720x1280x24 -nolisten tcp >"$ROOT/xvfb.log" 2>&1 &
sleep 1
fluxbox >"$ROOT/fluxbox.log" 2>&1 &
sleep 1
scrcpy --serial "$SERIAL" --no-audio --stay-awake --window-borderless --window-x=0 --window-y=0 --window-width=720 --window-height=1280 >"$ROOT/scrcpy.log" 2>&1 &
sleep 3
x11vnc -display :99 -forever -shared -nopw -localhost -rfbport 5900 >"$ROOT/x11vnc.log" 2>&1 &
sleep 2
websockify --web=/usr/share/novnc 6080 localhost:5900 >"$ROOT/novnc.log" 2>&1 &
sleep 2
cloudflared tunnel --no-autoupdate --url http://127.0.0.1:6080 >"$ROOT/tunnel.log" 2>&1 &

PHONE_URL=""
for _ in $(seq 1 60); do
  PHONE_URL=$(grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' "$ROOT/tunnel.log" | tail -1 || true)
  [ -n "$PHONE_URL" ] && break
  sleep 2
done

if [ -z "$PHONE_URL" ]; then
  echo 'ERROR: Cloudflare phone tunnel did not start.'
  cat "$ROOT/tunnel.log" || true
  exit 1
fi

FULL_URL="${PHONE_URL}/vnc.html?autoconnect=true&resize=scale&quality=6&compression=6"
echo "TAKARADA_PHONE_URL=$FULL_URL"
echo "Virtual Android phone is ready."
echo "Android: $($ADB -s "$SERIAL" shell getprop ro.build.version.release | tr -d '\r')"
echo "Aurora: $($ADB -s "$SERIAL" shell pm path com.aurora.store 2>/dev/null | head -1 | tr -d '\r')"
echo "Display: $($ADB -s "$SERIAL" shell pm path com.takarada.display 2>/dev/null | head -1 | tr -d '\r')"

# Put Aurora Store in front for first-time TikTok installation/login.
$ADB -s "$SERIAL" shell monkey -p com.aurora.store -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true

# Keep the free runner alive while the virtual phone is being used.
# Leave enough time for the action to shut the emulator down cleanly and save state.
END=$((SECONDS + 18600))
while [ $SECONDS -lt $END ]; do
  sleep 60
  $ADB -s "$SERIAL" shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1 || true
done

# Ask the emulator to persist a snapshot before the runner exits.
$ADB -s "$SERIAL" emu avd snapshot save takarada >/dev/null 2>&1 || true
sync
