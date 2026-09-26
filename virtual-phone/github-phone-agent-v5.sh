#!/usr/bin/env bash
set -euo pipefail

ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-emulator-5554}
BRANCH=takarada-virtual-phone
CMD_PATH=virtual-phone/assistant-command.json
SCREEN_PATH=virtual-phone/runtime/assistant-screen.png
UI_PATH=virtual-phone/runtime/assistant-ui.txt
STATUS_PATH=virtual-phone/runtime/assistant-status.txt
ROOT=/tmp/takarada-assistant-control
mkdir -p "$ROOT"

refresh_serial() {
  local found
  found=$($ADB devices 2>/dev/null | awk '$2=="device" && $1 ~ /^emulator-/ {print $1; exit}')
  if [ -n "$found" ]; then SERIAL="$found"; export ANDROID_SERIAL="$SERIAL"; fi
}


write_repo_file() {
  local path="$1" file="$2" msg="$3" sha payload
  sha=$(gh api "repos/$GITHUB_REPOSITORY/contents/$path?ref=$BRANCH" --jq '.sha // empty' 2>/dev/null || true)
  payload="$ROOT/payload.json"
  python3 - "$file" "$msg" "$BRANCH" "$sha" > "$payload" <<'PY'
import base64, json, sys
file_path, msg, branch, sha = sys.argv[1:5]
with open(file_path,'rb') as f:
    content=base64.b64encode(f.read()).decode()
obj={"message":msg,"content":content,"branch":branch}
if sha:
    obj["sha"]=sha
json.dump(obj,sys.stdout,separators=(',',':'))
PY
  gh api --method PUT "repos/$GITHUB_REPOSITORY/contents/$path" --input "$payload" >/dev/null
}
capture_screen() {
  refresh_serial
  local hostdir="$ROOT/hostshot" shot
  mkdir -p "$hostdir"
  rm -f "$hostdir"/*.png >/dev/null 2>&1 || true
  if timeout 20s "$ADB" -s "$SERIAL" emu screenrecord screenshot "$hostdir" >/dev/null 2>&1; then
    shot=$(find "$hostdir" -maxdepth 1 -type f -name '*.png' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)
    if [ -n "$shot" ] && [ -s "$shot" ]; then cp "$shot" "$ROOT/screen.png"; return 0; fi
  fi
  timeout 20s "$ADB" -s "$SERIAL" exec-out screencap -p > "$ROOT/screen.png" || true
}

capture_ui() {
  refresh_serial
  timeout 20s "$ADB" -s "$SERIAL" shell uiautomator dump /sdcard/window.xml >/dev/null 2>&1 || true
  timeout 20s "$ADB" -s "$SERIAL" pull /sdcard/window.xml "$ROOT/window.xml" >/dev/null 2>&1 || true
  python3 - "$ROOT/window.xml" > "$ROOT/ui.txt" <<'PY'
import sys, xml.etree.ElementTree as ET
try: root=ET.parse(sys.argv[1]).getroot()
except Exception: raise SystemExit
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
        label=' '.join((text or desc or rid or cls).split())[:180]
        rows.append(f'{label} | {cls} | {bounds} | click={str(clickable).lower()}')
print('\n'.join(rows[:220]))
PY
}

publish_state() {
  local seq="$1" note="${2:-ok}"
  printf 'seq=%s\nnote=%s\nrun=%s\nutc=%s\n' "$seq" "$note" "${GITHUB_RUN_ID:-unknown}" "$(date -u +%FT%TZ)" > "$ROOT/status.txt"
  write_repo_file "$STATUS_PATH" "$ROOT/status.txt" "Takarada assistant status seq $seq"
  capture_screen || true
  capture_ui || true
  [ -s "$ROOT/screen.png" ] && write_repo_file "$SCREEN_PATH" "$ROOT/screen.png" "Takarada assistant screen seq $seq"
  [ -s "$ROOT/ui.txt" ] && write_repo_file "$UI_PATH" "$ROOT/ui.txt" "Takarada assistant UI seq $seq" || true
  return 0
}

execute_command() {
  refresh_serial
  local json="$1" seq action x y x2 y2 duration key app text64 text
  seq=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("seq",0))' <<<"$json")
  action=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("action","screen"))' <<<"$json")
  case "$action" in
    tap)
      x=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("x",0)))' <<<"$json")
      y=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("y",0)))' <<<"$json")
      "$ADB" -s "$SERIAL" shell input tap "$x" "$y" ;;
    swipe)
      x=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("x1",0)))' <<<"$json")
      y=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("y1",0)))' <<<"$json")
      x2=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("x2",0)))' <<<"$json")
      y2=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("y2",0)))' <<<"$json")
      duration=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(int(d.get("duration",350)))' <<<"$json")
      "$ADB" -s "$SERIAL" shell input swipe "$x" "$y" "$x2" "$y2" "$duration" ;;
    key)
      key=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("key","KEYCODE_BACK"))' <<<"$json")
      "$ADB" -s "$SERIAL" shell input keyevent "$key" ;;
    launch)
      app=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("app","tiktok"))' <<<"$json")
      if [ "$app" = "tiktok" ]; then
        "$ADB" -s "$SERIAL" shell monkey -p com.zhiliaoapp.musically -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
      elif [ "$app" = "feed" ]; then
        "$ADB" -s "$SERIAL" shell am start -n com.takarada.display/.MainActivity --es url "${TAKARADA_FEED_URL:-https://takarada-cloud-live.onrender.com/preview}" >/dev/null 2>&1 || true
      fi ;;
    url)
      text64=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("url_b64",""))' <<<"$json")
      text=$(printf '%s' "$text64" | base64 -d 2>/dev/null || true)
      "$ADB" -s "$SERIAL" shell am start -a android.intent.action.VIEW -d "$text" >/dev/null 2>&1 || true ;;
    text)
      text64=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("text_b64",""))' <<<"$json")
      text=$(printf '%s' "$text64" | base64 -d 2>/dev/null || true)
      text=${text// /%s}
      "$ADB" -s "$SERIAL" shell input text "$text" ;;
    host_install_tiktok)
      refresh_serial
      host_apk="/tmp/takarada-phone-v2/tiktok.apk"
      for _ in $(seq 1 180); do
        [ -s "$host_apk" ] && [ "$(stat -c '%s' "$host_apk" 2>/dev/null || echo 0)" -gt 100000000 ] && break
        sleep 2
      done
      if [ ! -s "$host_apk" ]; then
        publish_state "$seq" "host_apk_missing"
        return
      fi
      actual_sha=$(sha256sum "$host_apk" | awk '{print $1}')
      if [ "$actual_sha" != "fbd8bf71e8150019fcafe23afc061d0b54906b5d8d8a37c070a70b6f3f431a0c" ]; then
        publish_state "$seq" "host_apk_sha_mismatch:$actual_sha"
        return
      fi
      pkill -f 'python3 -m http.server 8766' >/dev/null 2>&1 || true
      (cd /tmp/takarada-phone-v2 && nohup python3 -m http.server 8766 --bind 0.0.0.0 >/tmp/takarada-apk-http.log 2>&1 &)
      sleep 2
      remote_apk="/data/local/tmp/takarada-tiktok.apk"
      "$ADB" -s "$SERIAL" shell rm -f "$remote_apk" >/dev/null 2>&1 || true
      if "$ADB" -s "$SERIAL" shell 'command -v curl >/dev/null 2>&1'; then
        "$ADB" -s "$SERIAL" shell "curl -fL --retry 3 -o '$remote_apk' 'http://10.0.2.2:8766/tiktok.apk'" >/tmp/takarada-device-fetch.log 2>&1 || true
      else
        "$ADB" -s "$SERIAL" shell "toybox wget -O '$remote_apk' 'http://10.0.2.2:8766/tiktok.apk'" >/tmp/takarada-device-fetch.log 2>&1 || true
      fi
      remote_size=$("$ADB" -s "$SERIAL" shell stat -c %s "$remote_apk" 2>/dev/null | tr -d '\r' || echo 0)
      if [ "${remote_size:-0}" -lt 100000000 ]; then
        publish_state "$seq" "device_download_failed:$remote_size"
        return
      fi
      "$ADB" -s "$SERIAL" shell pm install -r "$remote_apk" >/tmp/takarada-device-install.log 2>&1 || true
      if "$ADB" -s "$SERIAL" shell pm path com.zhiliaoapp.musically >/dev/null 2>&1; then
        "$ADB" -s "$SERIAL" shell monkey -p com.zhiliaoapp.musically -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
        publish_state "$seq" "tiktok_installed_local"
      else
        publish_state "$seq" "tiktok_local_install_failed"
      fi
      return
      ;;
    install_apk)
      refresh_serial
      apk_path=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("path","/sdcard/Download/tiktok-45.5.4.apk"))' <<<"$json")
      host_apk="$ROOT/manual-install.apk"
      "$ADB" -s "$SERIAL" pull "$apk_path" "$host_apk" >/dev/null 2>&1 || true
      if [ -s "$host_apk" ]; then
        "$ADB" -s "$SERIAL" install -r "$host_apk" >/tmp/takarada-install.log 2>&1 || true
      fi
      ;;
    screen|report) : ;;
    *) publish_state "$seq" "unknown_action:$action"; return ;;
  esac
  sleep 2
  publish_state "$seq" "$action"
}

for _ in $(seq 1 45); do
  refresh_serial
  if [ -n "$SERIAL" ] && "$ADB" -s "$SERIAL" get-state >/dev/null 2>&1; then break; fi
  sleep 2
done
sleep 8
publish_state 0 boot

LAST_SEQ=0
END=$((SECONDS + 18600))
while [ $SECONDS -lt $END ]; do
  refresh_serial
  RAW=$(gh api "repos/$GITHUB_REPOSITORY/contents/$CMD_PATH?ref=$BRANCH" --jq '.content // empty' 2>/dev/null || true)
  if [ -n "$RAW" ]; then
    printf '%s' "$RAW" | tr -d '\n' | base64 -d > "$ROOT/command.json" 2>/dev/null || true
    if [ -s "$ROOT/command.json" ]; then
      SEQ=$(python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("seq",0)))' < "$ROOT/command.json" 2>/dev/null || echo 0)
      if [ "$SEQ" -gt "$LAST_SEQ" ]; then
        LAST_SEQ="$SEQ"
        execute_command "$(cat "$ROOT/command.json")" || publish_state "$SEQ" command_error
      fi
    fi
  fi
  sleep 2
done

