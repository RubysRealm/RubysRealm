#!/usr/bin/env bash
set -euo pipefail
curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/chrome.deb
rm -rf .chrome
mkdir -p .chrome
dpkg-deb -x /tmp/chrome.deb .chrome
curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o ./yt-dlp
chmod +x ./yt-dlp
"$PWD/.chrome/opt/google/chrome/google-chrome" --version
./yt-dlp --version
