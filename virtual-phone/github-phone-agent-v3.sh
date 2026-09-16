#!/usr/bin/env bash
set -euo pipefail

ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-emulator-5554}
ROOT=/tmp/takarada-phone-v3
mkdir -p "$ROOT"

if [ -z "${GH_TOKEN:-}" ] || [ -z "${GITHUB_REPOSITORY:-}" ] || [ -z "${TRIGGER_ISSUE:-}" ]; then
  echo 'Missing required GitHub session variables' >&2
  exit 2
fi

post_comment_v3() {
  local body=$1
  gh api --method POST "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE/comments" -f body="$body" >/dev/null
}

verify_and_publish() {
  local url=$1
  local provider=$2
  local attempt=${3:-1}
  for _ in $(seq 1 20); do
    if curl -fsS --max-time 12 "$url/" >/dev/null 2>&1; then
      post_comment_v3 "TAKARADA_REMOTE_URL|$url"
      post_comment_v3 "TAKARADA_REMOTE_STATUS|verified_public|provider=$provider|attempt=$attempt"
      return 0
    fi
    sleep 2
  done
  return 1
}

start_secure_remote_handshake() {
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$ROOT/remote_private.pem" >/dev/null 2>&1
  openssl pkey -in "$ROOT/remote_private.pem" -pubout -out "$ROOT/remote_public.pem" >/dev/null 2>&1
  local pub_b64
  pub_b64=$(base64 -w0 "$ROOT/remote_public.pem")
  post_comment_v3 "TAKARADA_REMOTE_KEY|$pub_b64"

  (
    local auth_path="virtual-phone/remote-auth-${TRIGGER_ISSUE}.txt"
    local outer secret url pid attempt
    for _ in $(seq 1 900); do
      outer=$(gh api "repos/$GITHUB_REPOSITORY/contents/$auth_path?ref=takarada-virtual-phone" --jq '.content // empty' 2>/dev/null || true)
      if [ -n "$outer" ]; then
        printf '%s' "$outer" | tr -d '\n' | base64 -d > "$ROOT/auth_file.txt" 2>/dev/null || true
        if [ -s "$ROOT/auth_file.txt" ]; then
          base64 -d "$ROOT/auth_file.txt" > "$ROOT/auth_cipher.bin" 2>/dev/null || true
          if [ -s "$ROOT/auth_cipher.bin" ]; then
            openssl pkeyutl -decrypt -inkey "$ROOT/remote_private.pem" -pkeyopt rsa_padding_mode:oaep -in "$ROOT/auth_cipher.bin" -out "$ROOT/remote_secret.txt" 2>/dev/null || true
            if [ -s "$ROOT/remote_secret.txt" ]; then
              secret=$(tr -d '\r\n' < "$ROOT/remote_secret.txt")
              if [ ${#secret} -ge 24 ]; then break; fi
            fi
          fi
        fi
      fi
      sleep 2
    done

    if [ ! -s "$ROOT/remote_secret.txt" ]; then
      post_comment_v3 'TAKARADA_REMOTE_ERROR|auth_not_received'
      exit 0
    fi

    secret=$(tr -d '\r\n' < "$ROOT/remote_secret.txt")
    export TAKARADA_REMOTE_SECRET="$secret"
    export TAKARADA_REMOTE_PORT=8765
    export ADB SERIAL ANDROID_SERIAL="$SERIAL"
    python3 virtual-phone/secure_phone_remote.py >"$ROOT/remote-server.log" 2>&1 &
    echo $! > "$ROOT/remote-server.pid"

    for _ in $(seq 1 30); do
      curl -fsS http://127.0.0.1:8765/ >/dev/null 2>&1 && break
      sleep 1
    done
    if ! curl -fsS http://127.0.0.1:8765/ >/dev/null 2>&1; then
      post_comment_v3 'TAKARADA_REMOTE_ERROR|local_controller_failed'
      exit 0
    fi

    # Primary: Cloudflare Quick Tunnel. Verify from the runner before publishing.
    if curl -fsSL --retry 4 --retry-all-errors -o "$ROOT/cloudflared" \
      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64; then
      chmod +x "$ROOT/cloudflared"
      for attempt in 1 2 3; do
        if [ -f "$ROOT/cloudflared.pid" ]; then
          pid=$(cat "$ROOT/cloudflared.pid" 2>/dev/null || true)
          [ -n "$pid" ] && kill "$pid" >/dev/null 2>&1 || true
        fi
        : > "$ROOT/cloudflared.log"
        "$ROOT/cloudflared" tunnel --protocol http2 --url http://127.0.0.1:8765 --no-autoupdate >"$ROOT/cloudflared.log" 2>&1 &
        echo $! > "$ROOT/cloudflared.pid"

        url=''
        for _ in $(seq 1 45); do
          url=$(grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' "$ROOT/cloudflared.log" 2>/dev/null | head -1 || true)
          [ -n "$url" ] && break
          sleep 1
        done
        if [ -n "$url" ] && verify_and_publish "$url" cloudflare "$attempt"; then
          exit 0
        fi
        post_comment_v3 "TAKARADA_REMOTE_STATUS|retrying_tunnel|provider=cloudflare|attempt=$attempt"
      done
    else
      post_comment_v3 'TAKARADA_REMOTE_STATUS|cloudflare_download_failed'
    fi

    # Fallback: localhost.run reverse SSH tunnel. This keeps the same password-protected controller.
    if command -v ssh >/dev/null 2>&1; then
      : > "$ROOT/localhost-run.log"
      ssh -T \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o ServerAliveInterval=30 \
        -o ExitOnForwardFailure=yes \
        -R 80:127.0.0.1:8765 nokey@localhost.run >"$ROOT/localhost-run.log" 2>&1 &
      echo $! > "$ROOT/localhost-run.pid"

      url=''
      for _ in $(seq 1 60); do
        url=$(grep -Eo 'https://[A-Za-z0-9.-]+' "$ROOT/localhost-run.log" 2>/dev/null | grep -Ev 'localhost.run/?$' | head -1 || true)
        [ -n "$url" ] && break
        sleep 1
      done
      if [ -n "$url" ] && verify_and_publish "$url" localhost-run 1; then
        exit 0
      fi
      post_comment_v3 'TAKARADA_REMOTE_STATUS|fallback_tunnel_failed|provider=localhost-run'
    fi

    post_comment_v3 'TAKARADA_REMOTE_ERROR|public_tunnel_unreachable'
  ) &
}

# Preserve the existing automatic dismissal of Android's one-time full-screen notice.
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

start_secure_remote_handshake
exec bash virtual-phone/github-phone-agent-v2.sh
