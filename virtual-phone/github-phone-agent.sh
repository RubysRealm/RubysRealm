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

curl -fL --retry 3 \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H 'Accept: application/vnd.github+json' \
  -o "$ROOT/display-artifact.zip" \
  "https://api.github.com/repos/$GITHUB_REPOSITORY/actions/artifacts/$APK_ARTIFACT_ID/zip"
unzip -jo "$ROOT/display-artifact.zip" 'app-debug.apk' -d "$ROOT"
printf '%s  %s\n' "$APK_SHA256" "$ROOT/app-debug.apk" | sha256sum -c -
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
        label=' '.join(label.split())[:140]
        rows.append(f'{label} | {cls} | {bounds} | click={str(clickable).lower()}')
print('\n'.join(rows[:120]))
PY
    if [ -s "$ROOT/ui.txt" ]; then
      UI=$(cat "$ROOT/ui.txt")
      post_comment "TAKARADA_UI|$seq
$UI"
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

post_comment "TAKARADA_PHONE_READY|KEY_RSA_OAEP|$KEY_CIPHER|RUN_ID|${GITHUB_RUN_ID:-unknown}"

$ADB -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "$FEED_URL" >/dev/null 2>&1 || true
sleep 2
$ADB -s "$SERIAL" shell input keyevent KEYCODE_HOME || true
sleep 1
report_state 0

# Aurora remains a fallback; TikTok itself will be sourced from TikTok's official download page first.
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
        url)
          URL=$(printf '%s' "$a" | base64 -d 2>/dev/null || true)
          $ADB -s "$SERIAL" shell am start -a android.intent.action.VIEW -d "$URL" >/dev/null 2>&1 || true
          ;;
        install_latest_apk)
          APK=$($ADB -s "$SERIAL" shell 'ls -t /sdcard/Download/*.apk 2>/dev/null | head -1' | tr -d '\r' || true)
          if [ -n "$APK" ]; then
            $ADB -s "$SERIAL" shell pm install -r "$APK" >/dev/null 2>&1 || true
          fi
          ;;
        feed)
          $ADB -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "$FEED_URL" >/dev/null 2>&1 || true
          ;;
        report)
          ;;
        *)
          post_comment "TAKARADA_AGENT_ERROR|$seq|unknown_action|$action"
          ;;
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
