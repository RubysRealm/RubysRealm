#!/usr/bin/env bash
set -euo pipefail

ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-emulator-5554}
FEED_URL=${TAKARADA_FEED_URL:-https://takarada-cloud-live.onrender.com/preview}
ROOT=/tmp/takarada-phone-agent
APK_ARTIFACT_ID=10420064382
APK_SHA256=e549269ce8a988b7faf62d342c90c7488ad270dd9efecb8d676a6e44c6d39a16
mkdir -p "$ROOT"

if [ -z "${GH_TOKEN:-}" ] || [ -z "${GITHUB_REPOSITORY:-}" ] || [ -z "${TRIGGER_ISSUE:-}" ]; then
  echo 'Missing GH_TOKEN/GITHUB_REPOSITORY/TRIGGER_ISSUE' >&2
  exit 2
fi

$ADB -s "$SERIAL" wait-for-device
$ADB -s "$SERIAL" shell wm size 720x1280 || true
$ADB -s "$SERIAL" shell wm density 320 || true
$ADB -s "$SERIAL" shell settings put system screen_off_timeout 2147483647 || true
$ADB -s "$SERIAL" shell svc power stayon true || true

# Download the exact APK produced by GitHub Actions instead of moving binary
# bytes through the connector. Verify it byte-for-byte before installation.
curl -fL --retry 3 \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H 'Accept: application/vnd.github+json' \
  -o "$ROOT/display-artifact.zip" \
  "https://api.github.com/repos/$GITHUB_REPOSITORY/actions/artifacts/$APK_ARTIFACT_ID/zip"
unzip -jo "$ROOT/display-artifact.zip" 'app-debug.apk' -d "$ROOT"
printf '%s  %s\n' "$APK_SHA256" "$ROOT/app-debug.apk" | sha256sum -c -
$ADB -s "$SERIAL" install -r "$ROOT/app-debug.apk"

# Session screenshot encryption key: only the matching private key outside the
# runner can decrypt this key. Screenshots posted to the public issue remain opaque.
SESSION_KEY_HEX=$(openssl rand -hex 32)
KEY_CIPHER=$(printf '%s' "$SESSION_KEY_HEX" | openssl pkeyutl -encrypt -pubin -inkey virtual-phone/phone_access_public.pem -pkeyopt rsa_padding_mode:oaep | base64 -w0)

post_comment() {
  local body=$1
  gh api --method POST "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE/comments" -f body="$body" >/dev/null
}

post_screen() {
  local seq=${1:-0}
  $ADB -s "$SERIAL" exec-out screencap -p > "$ROOT/screen.png"
  python3 - "$ROOT/screen.png" "$ROOT/screen.jpg" <<'PY'
from PIL import Image
import sys
src,dst=sys.argv[1],sys.argv[2]
im=Image.open(src).convert('RGB')
im.thumbnail((360,640), Image.Resampling.LANCZOS)
im.save(dst,'JPEG',quality=46,optimize=True,progressive=True)
PY
  local iv data
  iv=$(openssl rand -hex 16)
  openssl enc -aes-256-cbc -K "$SESSION_KEY_HEX" -iv "$iv" -in "$ROOT/screen.jpg" -out "$ROOT/screen.enc"
  data=$(base64 -w0 "$ROOT/screen.enc")
  post_comment "TAKARADA_SCREEN|$seq|$iv|$data"
}

post_comment "TAKARADA_PHONE_READY|KEY_RSA_OAEP|$KEY_CIPHER|RUN_ID|${GITHUB_RUN_ID:-unknown}"

# Initialize feed, but return to Android home so first screenshot is easy to read.
$ADB -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "$FEED_URL" >/dev/null 2>&1 || true
sleep 2
$ADB -s "$SERIAL" shell input keyevent KEYCODE_HOME || true
sleep 1
post_screen 0

# Best-effort Aurora Store install. Failure never kills the control agent.
(
  AURORA="$ROOT/aurora.apk"
  if curl -fL --retry 2 --connect-timeout 15 --max-time 90 -o "$AURORA" https://f-droid.org/repo/com.aurora.store_76.apk; then
    $ADB -s "$SERIAL" install -r "$AURORA" >/dev/null 2>&1 || true
  fi
) &

LAST_SEQ=0
END=$((SECONDS + 18600))
while [ $SECONDS -lt $END ]; do
  BODY=$(gh api "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE" --jq '.body // ""' 2>/dev/null || true)
  if [[ "$BODY" == TAKARADA_CMD\|* ]]; then
    IFS='|' read -r marker seq action a b c d e <<< "$BODY"
    if [[ "$seq" =~ ^[0-9]+$ ]] && [ "$seq" -gt "$LAST_SEQ" ]; then
      case "$action" in
        tap)
          $ADB -s "$SERIAL" shell input tap "$a" "$b" || true
          ;;
        swipe)
          $ADB -s "$SERIAL" shell input swipe "$a" "$b" "$c" "$d" "${e:-350}" || true
          ;;
        text)
          TEXT=$(printf '%s' "$a" | base64 -d 2>/dev/null || true)
          TEXT=${TEXT// /%s}
          $ADB -s "$SERIAL" shell input text "$TEXT" || true
          ;;
        key)
          $ADB -s "$SERIAL" shell input keyevent "$a" || true
          ;;
        back)
          $ADB -s "$SERIAL" shell input keyevent KEYCODE_BACK || true
          ;;
        home)
          $ADB -s "$SERIAL" shell input keyevent KEYCODE_HOME || true
          ;;
        enter)
          $ADB -s "$SERIAL" shell input keyevent KEYCODE_ENTER || true
          ;;
        launch)
          $ADB -s "$SERIAL" shell monkey -p "$a" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
          ;;
        feed)
          $ADB -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "$FEED_URL" >/dev/null 2>&1 || true
          ;;
        screenshot)
          ;;
        *)
          post_comment "TAKARADA_AGENT_ERROR|$seq|unknown_action|$action"
          ;;
      esac
      LAST_SEQ=$seq
      sleep 1
      post_screen "$seq" || post_comment "TAKARADA_AGENT_ERROR|$seq|screenshot_failed"
    fi
  fi
  sleep 2
done

$ADB -s "$SERIAL" emu avd snapshot save takarada >/dev/null 2>&1 || true
sync
