#!/usr/bin/env bash
set -euo pipefail

PHONE_ROOT=${PHONE_ROOT:-/opt/takarada-phone}
ANDROID_IMAGE=${ANDROID_IMAGE:-redroid/redroid:12.0.0_64only-latest}
ADB_SERIAL=${ADB_SERIAL:-127.0.0.1:5555}
WIDTH=${WIDTH:-720}
HEIGHT=${HEIGHT:-1280}
DPI=${DPI:-320}

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl docker.io android-tools-adb xvfb fluxbox x11vnc novnc websockify scrcpy python3 openssl linux-modules-extra-"$(uname -r)" || \
  apt-get install -y ca-certificates curl docker.io android-tools-adb xvfb fluxbox x11vnc novnc websockify scrcpy python3 openssl
systemctl enable --now docker

mkdir -p "$PHONE_ROOT" "$PHONE_ROOT/android-data" "$PHONE_ROOT/run" "$PHONE_ROOT/apks"

# ReDroid uses the host kernel. Binder is the only Android-specific kernel feature
# we need here; this avoids a heavyweight nested Android emulator.
modprobe binder_linux devices="binder,hwbinder,vndbinder" 2>/dev/null || modprobe binder_linux
printf '%s\n' binder_linux >/etc/modules-load.d/takarada-redroid.conf

if ! docker inspect takarada-redroid >/dev/null 2>&1; then
  docker run -d \
    --name takarada-redroid \
    --privileged \
    --restart unless-stopped \
    -p 127.0.0.1:5555:5555 \
    -v "$PHONE_ROOT/android-data:/data" \
    "$ANDROID_IMAGE" \
    androidboot.redroid_width="$WIDTH" \
    androidboot.redroid_height="$HEIGHT" \
    androidboot.redroid_dpi="$DPI" \
    androidboot.redroid_gpu_mode=guest
else
  docker start takarada-redroid >/dev/null || true
fi

for i in $(seq 1 90); do
  adb connect "$ADB_SERIAL" >/dev/null 2>&1 || true
  if adb -s "$ADB_SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' | grep -q '^1$'; then
    break
  fi
  sleep 2
done

adb -s "$ADB_SERIAL" shell wm size "${WIDTH}x${HEIGHT}" || true
adb -s "$ADB_SERIAL" shell wm density "$DPI" || true
adb -s "$ADB_SERIAL" shell settings put system screen_off_timeout 2147483647 || true
adb -s "$ADB_SERIAL" shell svc power stayon true || true

# Install Aurora Store from F-Droid so TikTok can be obtained from Google Play
# without bundling or trusting a random third-party TikTok APK mirror.
AURORA_APK="$PHONE_ROOT/apks/AuroraStore-4.8.4.apk"
if ! adb -s "$ADB_SERIAL" shell pm path com.aurora.store 2>/dev/null | grep -q package:; then
  curl -fL --retry 3 -o "$AURORA_APK" "https://f-droid.org/repo/com.aurora.store_76.apk"
  adb -s "$ADB_SERIAL" install -r "$AURORA_APK"
fi

cat >/usr/local/bin/takarada-install-apk <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ $# -ne 1 ]; then echo "Usage: takarada-install-apk /path/to/app.apk" >&2; exit 2; fi
adb connect 127.0.0.1:5555 >/dev/null 2>&1 || true
exec adb -s 127.0.0.1:5555 install -r "$1"
EOF
chmod +x /usr/local/bin/takarada-install-apk

if [ ! -f "$PHONE_ROOT/vnc.pass" ]; then
  VNC_PASSWORD=$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 16)
  x11vnc -storepasswd "$VNC_PASSWORD" "$PHONE_ROOT/vnc.pass" >/dev/null
  chmod 600 "$PHONE_ROOT/vnc.pass"
  printf '%s\n' "$VNC_PASSWORD" >"$PHONE_ROOT/vnc-password.txt"
  chmod 600 "$PHONE_ROOT/vnc-password.txt"
fi

cat >/usr/local/bin/takarada-phone-ui <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export DISPLAY=:99
ADB_SERIAL=${ADB_SERIAL:-127.0.0.1:5555}
WIDTH=${WIDTH:-720}
HEIGHT=${HEIGHT:-1280}
PHONE_ROOT=${PHONE_ROOT:-/opt/takarada-phone}

adb connect "$ADB_SERIAL" >/dev/null 2>&1 || true
adb -s "$ADB_SERIAL" wait-for-device
Xvfb :99 -screen 0 "${WIDTH}x${HEIGHT}x24" -nolisten tcp &
sleep 1
fluxbox >/tmp/takarada-fluxbox.log 2>&1 &
sleep 1
x11vnc -display :99 -forever -shared -rfbauth "$PHONE_ROOT/vnc.pass" -rfbport 5900 -localhost >/tmp/takarada-x11vnc.log 2>&1 &
sleep 1
websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/takarada-novnc.log 2>&1 &
sleep 1
exec scrcpy -s "$ADB_SERIAL" --no-audio --stay-awake --window-borderless --window-x=0 --window-y=0 --window-width="$WIDTH" --window-height="$HEIGHT"
EOF
chmod +x /usr/local/bin/takarada-phone-ui

cat >/etc/systemd/system/takarada-phone-ui.service <<EOF
[Unit]
Description=Takarada virtual Android phone UI
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=simple
Environment=PHONE_ROOT=$PHONE_ROOT
Environment=ADB_SERIAL=$ADB_SERIAL
Environment=WIDTH=$WIDTH
Environment=HEIGHT=$HEIGHT
ExecStart=/usr/local/bin/takarada-phone-ui
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Secure public access to noVNC through a Cloudflare Quick Tunnel. The URL is
# random and HTTPS. VNC itself is additionally password protected.
ARCH=$(dpkg --print-architecture)
if ! command -v cloudflared >/dev/null 2>&1; then
  case "$ARCH" in
    amd64) CF_ARCH=amd64 ;;
    arm64) CF_ARCH=arm64 ;;
    *) CF_ARCH=amd64 ;;
  esac
  curl -fsSL -o /tmp/cloudflared.deb "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}.deb"
  dpkg -i /tmp/cloudflared.deb || apt-get -f install -y
fi

cat >/etc/systemd/system/takarada-phone-tunnel.service <<'EOF'
[Unit]
Description=Takarada phone HTTPS tunnel
After=network-online.target takarada-phone-ui.service
Requires=takarada-phone-ui.service

[Service]
Type=simple
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:6080
Restart=always
RestartSec=5
StandardOutput=append:/var/log/takarada-phone-tunnel.log
StandardError=append:/var/log/takarada-phone-tunnel.log

[Install]
WantedBy=multi-user.target
EOF

cat >/usr/local/bin/takarada-phone-status <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
PHONE_ROOT=${PHONE_ROOT:-/opt/takarada-phone}
echo '=== Android ==='
adb -s 127.0.0.1:5555 shell getprop ro.build.version.release 2>/dev/null || true
adb -s 127.0.0.1:5555 shell getprop sys.boot_completed 2>/dev/null || true
echo '=== Aurora Store ==='
adb -s 127.0.0.1:5555 shell pm path com.aurora.store 2>/dev/null || true
echo '=== UI ==='
systemctl is-active takarada-phone-ui.service || true
echo '=== Browser URL ==='
grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' /var/log/takarada-phone-tunnel.log 2>/dev/null | tail -1 || true
echo '=== VNC password ==='
cat "$PHONE_ROOT/vnc-password.txt" 2>/dev/null || true
EOF
chmod +x /usr/local/bin/takarada-phone-status

systemctl daemon-reload
systemctl enable --now takarada-phone-ui.service takarada-phone-tunnel.service
sleep 5

echo
echo 'Takarada virtual phone bootstrap complete.'
/usr/local/bin/takarada-phone-status
