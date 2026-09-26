#!/usr/bin/env bash
set -euo pipefail

ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-emulator-5554}
FEED_URL=${TAKARADA_FEED_URL:-https://takarada-cloud-live.onrender.com/preview}
ROOT=/tmp/takarada-phone-v2
DISPLAY_ARTIFACT_ID=10420064382
DISPLAY_SHA256=e549269ce8a988b7faf62d342c90c7488ad270dd9efecb8d676a6e44c6d39a16
TIKTOK_URL='https://cdn.apkba.com/apps/apk/com.zhiliaoapp.musically?version=latest'
TIKTOK_PACKAGE='com.zhiliaoapp.musically'
TIKTOK_CERT_SHA256='9041803e91bcb814b4b4399fb5c85a91640b755e5e8ba76813814bf4cf2ab5ba'
mkdir -p "$ROOT"

refresh_serial() {
  local found
  found=$($ADB devices 2>/dev/null | awk '$2=="device" && $1 ~ /^emulator-/ {print $1; exit}')
  if [ -n "$found" ]; then SERIAL="$found"; export ANDROID_SERIAL="$SERIAL"; fi
}

adb_ready() {
  for _ in $(seq 1 45); do
    refresh_serial
    if [ -n "$SERIAL" ] && $ADB -s "$SERIAL" get-state >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  return 1
}


if [ -z "${GH_TOKEN:-}" ] || [ -z "${GITHUB_REPOSITORY:-}" ] || [ -z "${TRIGGER_ISSUE:-}" ]; then
  echo 'Missing required GitHub session variables' >&2
  exit 2
fi

post_comment() {
  local body=$1
  gh api --method POST "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE/comments" -f body="$body" >/dev/null
}

adb_ready || { echo "No Android emulator became ready" >&2; exit 3; }
$ADB -s "$SERIAL" shell wm size 720x1280 || true
$ADB -s "$SERIAL" shell wm density 320 || true
$ADB -s "$SERIAL" shell settings put system screen_off_timeout 2147483647 || true
$ADB -s "$SERIAL" shell svc power stayon true || true

curl -fsSL --retry 3 \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H 'Accept: application/vnd.github+json' \
  -o "$ROOT/display.zip" \
  "https://api.github.com/repos/$GITHUB_REPOSITORY/actions/artifacts/$DISPLAY_ARTIFACT_ID/zip"
unzip -jo "$ROOT/display.zip" 'app-debug.apk' -d "$ROOT" >/dev/null
printf '%s  %s\n' "$DISPLAY_SHA256" "$ROOT/app-debug.apk" | sha256sum -c -
$ADB -s "$SERIAL" install -r "$ROOT/app-debug.apk" >/dev/null

SESSION_KEY_HEX=$(openssl rand -hex 32)
KEY_CIPHER=$(printf '%s' "$SESSION_KEY_HEX" | openssl pkeyutl -encrypt -pubin -inkey virtual-phone/phone_access_public.pem -pkeyopt rsa_padding_mode:oaep | base64 -w0)
post_comment "TAKARADA_PHONE_READY_V2|KEY_RSA_OAEP|$KEY_CIPHER|RUN_ID|${GITHUB_RUN_ID:-unknown}"

publish_ui() {
  local seq=${1:-0}
  $ADB -s "$SERIAL" shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 || true
  $ADB -s "$SERIAL" pull /sdcard/window.xml "$ROOT/window.xml" >/dev/null 2>&1 || true
  [ -s "$ROOT/window.xml" ] || return 0
  python3 - "$ROOT/window.xml" > "$ROOT/ui.txt" <<'PY'
import sys, xml.etree.ElementTree as ET
try: root=ET.parse(sys.argv[1]).getroot()
except Exception: raise SystemExit
rows=[]
for n in root.iter('node'):
    a=n.attrib; text=(a.get('text') or '').strip(); desc=(a.get('content-desc') or '').strip()
    rid=(a.get('resource-id') or '').strip(); cls=(a.get('class') or '').split('.')[-1]
    bounds=a.get('bounds') or ''; clickable=a.get('clickable')=='true'
    if text or desc or clickable:
        label=' '.join((text or desc or rid or cls).split())[:180]
        rows.append(f'{label} | {cls} | {bounds} | click={str(clickable).lower()}')
print('\n'.join(rows[:170]))
PY
  [ -s "$ROOT/ui.txt" ] && post_comment "TAKARADA_UI|$seq
$(cat "$ROOT/ui.txt")"
}

capture_png() {
  local hostdir="$ROOT/hostshot"
  mkdir -p "$hostdir"
  rm -f "$hostdir"/*.png >/dev/null 2>&1 || true
  if $ADB -s "$SERIAL" emu screenrecord screenshot "$hostdir" >/dev/null 2>&1; then
    local shot
    shot=$(find "$hostdir" -maxdepth 1 -type f -name '*.png' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)
    if [ -n "$shot" ] && [ -s "$shot" ]; then
      cp "$shot" "$ROOT/full.png"
      return 0
    fi
  fi
  $ADB -s "$SERIAL" exec-out screencap -p > "$ROOT/full.png"
}

detect_qr() {
  local seq=${1:-0} qr iv data
  capture_png || return 0
  qr=$(zbarimg --quiet --raw "$ROOT/full.png" 2>/dev/null | head -1 || true)
  [ -n "$qr" ] || return 0
  iv=$(openssl rand -hex 16)
  printf '%s' "$qr" | openssl enc -aes-256-cbc -K "$SESSION_KEY_HEX" -iv "$iv" -out "$ROOT/qr.enc"
  data=$(base64 -w0 "$ROOT/qr.enc")
  post_comment "TAKARADA_QR|$seq|$iv|$data"
}

publish_screen() {
  local seq=${1:-0} iv data
  capture_png || return 0
  python3 - "$ROOT/full.png" "$ROOT/screen.jpg" <<'PY'
from PIL import Image
import sys
im=Image.open(sys.argv[1]).convert('RGB')
im.thumbnail((360,640), Image.Resampling.LANCZOS)
im.save(sys.argv[2],'JPEG',quality=42,optimize=True,progressive=True)
PY
  iv=$(openssl rand -hex 16)
  openssl enc -aes-256-cbc -K "$SESSION_KEY_HEX" -iv "$iv" -in "$ROOT/screen.jpg" -out "$ROOT/screen.enc"
  data=$(base64 -w0 "$ROOT/screen.enc")
  post_comment "TAKARADA_SCREEN|$seq|$iv|$data"
}

report_state() {
  refresh_serial
  local seq=${1:-0}
  publish_ui "$seq" || true
  detect_qr "$seq" || true
}

install_tiktok() {
  adb_ready || { post_comment "TAKARADA_AGENT_ERROR|adb_unavailable_before_tiktok_install"; return 1; }
  local apk="$ROOT/tiktok.apk" bt apksigner aapt signer package actual_sha out cert_out
  post_comment 'TAKARADA_STATUS|tiktok_download_started|source=verified_mirror'
  if ! curl -fL --retry 5 --retry-all-errors --retry-delay 3 --connect-timeout 30 --max-time 1500 \
      -A 'Mozilla/5.0 (Linux; Android 15; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36' \
      -o "$apk" "$TIKTOK_URL"; then
    post_comment 'TAKARADA_AGENT_ERROR|tiktok_download_failed'
    return 1
  fi
  actual_sha=$(sha256sum "$apk" | awk '{print $1}')
  bt="${ANDROID_HOME:-/usr/local/lib/android/sdk}/build-tools"
  apksigner=$(find "$bt" -type f -name apksigner | sort -V | tail -1)
  aapt=$(find "$bt" -type f -name aapt | sort -V | tail -1)
  if [ -z "$apksigner" ] || [ -z "$aapt" ]; then
    post_comment 'TAKARADA_AGENT_ERROR|android_verify_tools_missing'
    return 1
  fi
  if ! "$apksigner" verify "$apk" >/dev/null 2>&1; then
    post_comment "TAKARADA_AGENT_ERROR|tiktok_apk_signature_invalid|sha256=$actual_sha"
    return 1
  fi
  cert_out=$("$apksigner" verify --verbose --print-certs "$apk" 2>&1 || true)
  signer=$(printf '%s\n' "$cert_out" \
    | sed -nE 's/.*certificate SHA-256 digest:[[:space:]]*([0-9A-Fa-f:]+).*/\1/ip' \
    | head -1 \
    | tr -d ':' \
    | tr '[:upper:]' '[:lower:]')
  if [ -z "$signer" ]; then
    signer=$(printf '%s\n' "$cert_out" \
      | grep -Eio '[0-9a-f]{64}' \
      | head -1 \
      | tr '[:upper:]' '[:lower:]' || true)
  fi
  package=$("$aapt" dump badging "$apk" 2>/dev/null | sed -n "s/^package: name='\([^']*\)'.*/\1/p" | head -1)
  if [ "$package" != "$TIKTOK_PACKAGE" ]; then
    post_comment "TAKARADA_AGENT_ERROR|tiktok_package_mismatch|got=$package|sha256=$actual_sha"
    return 1
  fi
  if [ -z "$signer" ]; then
    safe_cert=$(printf '%s' "$cert_out" | tr '\n' ' ' | tr -cd '[:alnum:] #:=._,-' | cut -c1-900)
    post_comment "TAKARADA_AGENT_ERROR|tiktok_signer_unreadable|sha256=$actual_sha|apksigner=$safe_cert"
    return 1
  fi
  if [ "$signer" != "$TIKTOK_CERT_SHA256" ]; then
    post_comment "TAKARADA_AGENT_ERROR|tiktok_signer_mismatch|got=$signer|sha256=$actual_sha"
    return 1
  fi
  post_comment "TAKARADA_STATUS|tiktok_identity_verified|package=$package|cert=$signer|sha256=$actual_sha"
  local installed=0 attempt remote_apk=/data/local/tmp/takarada-tiktok.apk
  local host_bytes remote_bytes tcp_pid safe_out
  host_bytes=$(stat -c '%s' "$apk")
  for attempt in 1 2 3; do
    adb_ready || true
    $ADB -s "$SERIAL" shell rm -f "$remote_apk" >/dev/null 2>&1 || true
    python3 - "$apk" >"$ROOT/apk-tcp.log" 2>&1 <<'PY' &
import socket,sys
path=sys.argv[1]
srv=socket.socket()
srv.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
srv.bind(('0.0.0.0',8766))
srv.listen(1)
conn,_=srv.accept()
with conn, open(path,'rb') as f:
    while True:
        chunk=f.read(1024*1024)
        if not chunk: break
        conn.sendall(chunk)
srv.close()
PY
    tcp_pid=$!
    sleep 1
    out=''
    if timeout 240s $ADB -s "$SERIAL" shell sh -c \
      "'if toybox nc --help >/dev/null 2>&1; then toybox nc 10.0.2.2 8766 > $remote_apk; elif command -v nc >/dev/null 2>&1; then nc 10.0.2.2 8766 > $remote_apk; else exit 127; fi'" \
      >/dev/null 2>&1; then
      wait "$tcp_pid" >/dev/null 2>&1 || true
      remote_bytes=$($ADB -s "$SERIAL" shell sh -c "'wc -c < $remote_apk'" 2>/dev/null | tr -d '\r ' || true)
      if [ "$remote_bytes" = "$host_bytes" ]; then
        if out=$(timeout 240s $ADB -s "$SERIAL" shell pm install -r "$remote_apk" 2>&1); then
          if printf '%s' "$out" | grep -qi 'Success'; then installed=1; break; fi
        fi
      else
        out="tcp_size_mismatch host=$host_bytes remote=${remote_bytes:-missing}"
      fi
    else
      out='android_tcp_receive_failed_or_timed_out'
    fi
    kill "$tcp_pid" >/dev/null 2>&1 || true
    safe_out=$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-500)
    post_comment "TAKARADA_STATUS|tiktok_tcp_install_retry|attempt=$attempt|serial=$SERIAL|detail=$safe_out"
    sleep 4
  done
  kill "${tcp_pid:-}" >/dev/null 2>&1 || true
  $ADB -s "$SERIAL" shell rm -f "$remote_apk" >/dev/null 2>&1 || true
  if [ "$installed" != "1" ]; then
    out=$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-700)
    post_comment "TAKARADA_AGENT_ERROR|tiktok_tcp_install_failed|serial=$SERIAL|$out"
    return 1
  fi
  post_comment 'TAKARADA_STATUS|tiktok_verified_installed'
  return 0
}

$ADB -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "$FEED_URL" >/dev/null 2>&1 || true
sleep 2
$ADB -s "$SERIAL" shell input keyevent KEYCODE_HOME || true
report_state 0

# Preserve restored TikTok app data. Only install TikTok on a genuinely fresh phone.
if $ADB -s "$SERIAL" shell pm path "$TIKTOK_PACKAGE" >/dev/null 2>&1; then
  post_comment 'TAKARADA_STATUS|tiktok_existing_install_preserved'
  $ADB -s "$SERIAL" shell monkey -p "$TIKTOK_PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
  sleep 10
  report_state 1
else
  if install_tiktok; then
    $ADB -s "$SERIAL" shell monkey -p "$TIKTOK_PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
    sleep 10
    report_state 1
  fi
fi

LAST_SEQ=$(gh api "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE" --jq '.body // ""' 2>/dev/null | awk -F'|' '/^TAKARADA_CMD\|[0-9]+\|/ {print $2}' || true)
LAST_SEQ=${LAST_SEQ:-1}
END=$((SECONDS + 18600))
while [ $SECONDS -lt $END ]; do
  refresh_serial
  BODY=$(gh api "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE" --jq '.body // ""' 2>/dev/null || true)
  if [[ "$BODY" == TAKARADA_CMD\|* ]]; then
    IFS='|' read -r marker seq action a b c d e <<< "$BODY"
    if [[ "$seq" =~ ^[0-9]+$ ]] && [ "$seq" -gt "$LAST_SEQ" ]; then
      case "$action" in
        tap) $ADB -s "$SERIAL" shell input tap "$a" "$b" || true ;;
        swipe) $ADB -s "$SERIAL" shell input swipe "$a" "$b" "$c" "$d" "${e:-350}" || true ;;
        text)
          TEXT=$(printf '%s' "$a" | base64 -d 2>/dev/null || true); TEXT=${TEXT// /%s}
          $ADB -s "$SERIAL" shell input text "$TEXT" || true ;;
        key) $ADB -s "$SERIAL" shell input keyevent "$a" || true ;;
        back) $ADB -s "$SERIAL" shell input keyevent KEYCODE_BACK || true ;;
        home) $ADB -s "$SERIAL" shell input keyevent KEYCODE_HOME || true ;;
        enter) $ADB -s "$SERIAL" shell input keyevent KEYCODE_ENTER || true ;;
        launch) $ADB -s "$SERIAL" shell monkey -p "$a" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true ;;
        url)
          URL=$(printf '%s' "$a" | base64 -d 2>/dev/null || true)
          $ADB -s "$SERIAL" shell am start -a android.intent.action.VIEW -d "$URL" >/dev/null 2>&1 || true ;;
        tiktok) $ADB -s "$SERIAL" shell monkey -p "$TIKTOK_PACKAGE" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true ;;
        feed) $ADB -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "$FEED_URL" >/dev/null 2>&1 || true ;;
        screen) publish_screen "$seq" || true ;;
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
