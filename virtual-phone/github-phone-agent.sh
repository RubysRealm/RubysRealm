#!/usr/bin/env bash
set -euo pipefail

ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-emulator-5554}
FEED_URL=${TAKARADA_FEED_URL:-https://takarada-cloud-live.onrender.com/preview}
ROOT=/tmp/takarada-phone-agent
APK_ARTIFACT_ID=10420064382
DISPLAY_APK_SHA256=e549269ce8a988b7faf62d342c90c7488ad270dd9efecb8d676a6e44c6d39a16
TIKTOK_URL='https://d.apkpure.net/b/APK/com.zhiliaoapp.musically?version=latest'
TIKTOK_APK_SHA256='56dc6309c1d485aaa0f1b04d097d57364371c7241567156a70ce1bf373ee34ed'
TIKTOK_CERT_SHA256='9041803e91bcb814b4b4399fb5c85a91640b755e5e8ba76813814bf4cf2ab5ba'
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

# Install the verified Takarada display app.
curl -fL --retry 3 \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H 'Accept: application/vnd.github+json' \
  -o "$ROOT/display-artifact.zip" \
  "https://api.github.com/repos/$GITHUB_REPOSITORY/actions/artifacts/$APK_ARTIFACT_ID/zip"
unzip -jo "$ROOT/display-artifact.zip" 'app-debug.apk' -d "$ROOT"
printf '%s  %s\n' "$DISPLAY_APK_SHA256" "$ROOT/app-debug.apk" | sha256sum -c -
$ADB -s "$SERIAL" install -r "$ROOT/app-debug.apk"

SESSION_KEY_HEX=$(openssl rand -hex 32)
KEY_CIPHER=$(printf '%s' "$SESSION_KEY_HEX" | openssl pkeyutl -encrypt -pubin -inkey virtual-phone/phone_access_public.pem -pkeyopt rsa_padding_mode:oaep | base64 -w0)

post_comment() {
  local body=$1
  gh api --method POST "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE/comments" -f body="$body" >/dev/null
}

publish_ui() {
  local seq=${1:-0}
  $ADB -s "$SERIAL" shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 || true
  $ADB -s "$SERIAL" pull /sdcard/window.xml "$ROOT/window.xml" >/dev/null 2>&1 || true
  if [ -s "$ROOT/window.xml" ]; then
    python3 - "$ROOT/window.xml" > "$ROOT/ui.txt" <<'PY'
import sys, xml.etree.ElementTree as ET
p=sys.argv[1]
try:
    root=ET.parse(p).getroot()
except Exception:
    raise SystemExit
rows=[]
for n in root.iter('node'):
    a=n.attrib
    text=(a.get('text') or '').strip()
    desc=(a.get('content-desc') or '').strip()
    rid=(a.get('resource-id') or '').strip()
    cls=(a.get('class') or '').split('.')[-1]
    bounds=a.get('bounds') or ''
    clickable=a.get('clickable')=='true'
    if text or desc or clickable:
        label=text or desc or rid or cls
        label=' '.join(label.split())[:160]
        rows.append(f'{label} | {cls} | {bounds} | click={str(clickable).lower()}')
print('\n'.join(rows[:140]))
PY
    if [ -s "$ROOT/ui.txt" ]; then
      post_comment "TAKARADA_UI|$seq
$(cat "$ROOT/ui.txt")"
    fi
  fi
}

detect_qr() {
  local seq=${1:-0}
  $ADB -s "$SERIAL" exec-out screencap -p > "$ROOT/full.png" || return 0
  local qr iv data
  qr=$(zbarimg --quiet --raw "$ROOT/full.png" 2>/dev/null | head -1 || true)
  if [ -n "$qr" ]; then
    iv=$(openssl rand -hex 16)
    printf '%s' "$qr" | openssl enc -aes-256-cbc -K "$SESSION_KEY_HEX" -iv "$iv" -out "$ROOT/qr.enc"
    data=$(base64 -w0 "$ROOT/qr.enc")
    post_comment "TAKARADA_QR|$seq|$iv|$data"
  fi
}

report_state() {
  local seq=${1:-0}
  publish_ui "$seq" || true
  detect_qr "$seq" || true
}

install_tiktok() {
  local apk="$ROOT/tiktok.apk" signer apksigner
  post_comment 'TAKARADA_STATUS|tiktok_download_started'
  if ! curl -fL --retry 4 --retry-delay 3 --connect-timeout 30 --max-time 900 \
      -A 'Mozilla/5.0 (Linux; Android 15; Pixel 7 Pro) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36' \
      -o "$apk" "$TIKTOK_URL"; then
    post_comment 'TAKARADA_AGENT_ERROR|tiktok_download_failed'
    return 1
  fi
  if ! printf '%s  %s\n' "$TIKTOK_APK_SHA256" "$apk" | sha256sum -c -; then
    post_comment "TAKARADA_AGENT_ERROR|tiktok_hash_mismatch|$(sha256sum "$apk" | awk '{print $1}')"
    rm -f "$apk"
    return 1
  fi
  apksigner=$(find "${ANDROID_HOME:-/usr/local/lib/android/sdk}/build-tools" -type f -name apksigner | sort -V | tail -1)
  signer=$($apksigner verify --print-certs "$apk" 2>/dev/null | awk -F': ' '/Signer #1 certificate SHA-256 digest/ {print tolower($2); exit}')
  if [ "$signer" != "$TIKTOK_CERT_SHA256" ]; then
    post_comment 'TAKARADA_AGENT_ERROR|tiktok_signer_mismatch'
    rm -f "$apk"
    return 1
  fi
  if ! $ADB -s "$SERIAL" install -r "$apk"; then
    post_comment 'TAKARADA_AGENT_ERROR|tiktok_install_failed'
    return 1
  fi
  post_comment 'TAKARADA_STATUS|tiktok_verified_installed'
  return 0
}

post_comment "TAKARADA_PHONE_READY|KEY_RSA_OAEP|$KEY_CIPHER|RUN_ID|${GITHUB_RUN_ID:-unknown}"

# Put the display app on the phone, then install and open verified standard TikTok.
$ADB -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "$FEED_URL" >/dev/null 2>&1 || true
sleep 2
$ADB -s "$SERIAL" shell input keyevent KEYCODE_HOME || true
report_state 0

if install_tiktok; then
  $ADB -s "$SERIAL" shell monkey -p com.zhiliaoapp.musically -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
  sleep 6
  report_state 1
fi

LAST_SEQ=1
END=$((SECONDS + 18600))
while [ $SECONDS -lt $END ]; do
  BODY=$(gh api "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE" --jq '.body // ""' 2>/dev/null || true)
  if [[ "$BODY" == TAKARADA_CMD\|* ]]; then
    IFS='|' read -r marker seq action a b c d e <<< "$BODY"
    if [[ "$seq" =~ ^[0-9]+$ ]] && [ "$seq" -gt "$LAST_SEQ" ]; then
      case "$action" in
        tap) $ADB -s "$SERIAL" shell input tap "$a" "$b" || true ;;
        swipe) $ADB -s "$SERIAL" shell input swipe "$a" "$b" "$c" "$d" "${e:-350}" || true ;;
        text)
          TEXT=$(printf '%s' "$a" | base64 -d 2>/dev/null || true)
          TEXT=${TEXT// /%s}
          $ADB -s "$SERIAL" shell input text "$TEXT" || true
          ;;
        key) $ADB -s "$SERIAL" shell input keyevent "$a" || true ;;
        back) $ADB -s "$SERIAL" shell input keyevent KEYCODE_BACK || true ;;
        home) $ADB -s "$SERIAL" shell input keyevent KEYCODE_HOME || true ;;
        enter) $ADB -s "$SERIAL" shell input keyevent KEYCODE_ENTER || true ;;
        launch) $ADB -s "$SERIAL" shell monkey -p "$a" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true ;;
        url)
          URL=$(printf '%s' "$a" | base64 -d 2>/dev/null || true)
          $ADB -s "$SERIAL" shell am start -a android.intent.action.VIEW -d "$URL" >/dev/null 2>&1 || true
          ;;
        tiktok) $ADB -s "$SERIAL" shell monkey -p com.zhiliaoapp.musically -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true ;;
        feed) $ADB -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "$FEED_URL" >/dev/null 2>&1 || true ;;
        report) ;;
        *) post_comment "TAKARADA_AGENT_ERROR|$seq|unknown_action|$action" ;;
      esac
      LAST_SEQ=$seq
      sleep 2
      report_state "$seq"
    fi
  fi
  sleep 2
done

$ADB -s "$SERIAL" emu avd snapshot save takarada >/dev/null 2>&1 || true
sync
