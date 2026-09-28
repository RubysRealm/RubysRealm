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

# Expose Android directly through the secure ADB-backed web controller.
# This avoids scrcpy/X11/noVNC entirely.
REMOTE_SECRET=$(openssl rand -hex 12)
export TAKARADA_REMOTE_SECRET="$REMOTE_SECRET"
export TAKARADA_REMOTE_PORT=8765

python3 virtual-phone/secure_phone_remote.py >"$ROOT/direct-phone.log" 2>&1 &
DIRECT_PID=$!

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8765/ >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$DIRECT_PID" >/dev/null 2>&1; then
    echo 'ERROR: direct phone controller exited.'
    cat "$ROOT/direct-phone.log" || true
    exit 1
  fi
  sleep 1
done

cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8765 >"$ROOT/tunnel.log" 2>&1 &

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

SECRET_CIPHER=$(printf '%s' "$REMOTE_SECRET" | openssl pkeyutl -encrypt -pubin -inkey virtual-phone/phone_access_public.pem -pkeyopt rsa_padding_mode:oaep | base64 -w0)

if [ -n "${TRIGGER_ISSUE:-}" ] && [ -n "${GH_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
  BODY=$(cat <<EOF
TAKARADA_DIRECT_PHONE_READY
URL: $PHONE_URL
SECRET_RSA_OAEP: $SECRET_CIPHER
RUN_ID: ${GITHUB_RUN_ID:-unknown}
EOF
)
  gh api --method POST "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE/comments" -f body="$BODY" >/dev/null || echo 'WARNING: could not post direct phone access callback'
fi

# Keep the assistant controller alive beside the browser-controlled phone.
bash virtual-phone/github-phone-agent-v5.sh >"$ROOT/assistant-agent.log" 2>&1 &
ASSISTANT_AGENT_PID=$!

$ADB -s "$SERIAL" shell monkey -p com.zhiliaoapp.musically -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
sleep 2

# Keep the free runner alive while the virtual phone is being used.
END=$((SECONDS + 18600))
while [ $SECONDS -lt $END ]; do
  sleep 60
  $ADB -s "$SERIAL" shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1 || true
done

# Persist Android state before the runner exits.
$ADB -s "$SERIAL" emu avd snapshot save takarada >/dev/null 2>&1 || true
sync
