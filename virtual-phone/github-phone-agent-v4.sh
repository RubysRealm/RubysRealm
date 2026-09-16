#!/usr/bin/env bash
set -euo pipefail

ADB=${ADB:-adb}
SERIAL=${ANDROID_SERIAL:-emulator-5554}

if [ -z "${GH_TOKEN:-}" ] || [ -z "${GITHUB_REPOSITORY:-}" ] || [ -z "${TRIGGER_ISSUE:-}" ]; then
  echo 'Missing required GitHub session variables' >&2
  exit 2
fi

post_comment_v4() {
  gh api --method POST "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE/comments" -f body="$1" >/dev/null
}

save_phone_state() {
  "$ADB" -s "$SERIAL" shell sync >/dev/null 2>&1 || true
  "$ADB" -s "$SERIAL" emu avd snapshot save takarada >/dev/null 2>&1 || true
  sync
  post_comment_v4 'TAKARADA_STATUS|phone_state_saved'
}

bash virtual-phone/github-phone-agent-v3.sh &
AGENT_PID=$!
LAST_CTL=''

cleanup() {
  kill "$AGENT_PID" >/dev/null 2>&1 || true
  wait "$AGENT_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

while kill -0 "$AGENT_PID" >/dev/null 2>&1; do
  BODY=$(gh api "repos/$GITHUB_REPOSITORY/issues/$TRIGGER_ISSUE" --jq '.body // ""' 2>/dev/null || true)
  if [[ "$BODY" == TAKARADA_CTL\|* ]] && [ "$BODY" != "$LAST_CTL" ]; then
    LAST_CTL="$BODY"
    case "$BODY" in
      TAKARADA_CTL\|save)
        save_phone_state
        ;;
      TAKARADA_CTL\|save_finish)
        save_phone_state
        post_comment_v4 'TAKARADA_STATUS|phone_state_saved_finishing'
        kill "$AGENT_PID" >/dev/null 2>&1 || true
        wait "$AGENT_PID" >/dev/null 2>&1 || true
        trap - EXIT INT TERM
        exit 0
        ;;
    esac
  fi
  sleep 2
done

wait "$AGENT_PID"
trap - EXIT INT TERM
