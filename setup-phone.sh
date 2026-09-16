#!/usr/bin/env bash
set -euo pipefail
curl -fsSL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/chrome.deb
rm -rf .chrome
mkdir -p .chrome
dpkg-deb -x /tmp/chrome.deb .chrome
curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o ./yt-dlp
chmod +x ./yt-dlp

python3 - <<'PY'
from pathlib import Path
p = Path('phone-headless.js')
s = p.read_text()
s = s.replace(
    "const pending = /scan qr code|yt\\.be\\/activate|enter the code|sign in with (your )?phone/i.test(body);",
    "const pending = /scan qr code|yt\\.be\\/activate|enter the code/i.test(body);"
)
s = s.replace(
    "        '--disable-features=TranslateUI','--disable-background-networking','--disable-component-update','--disable-sync',",
    "        '--disable-features=TranslateUI','--disable-component-update','--disable-sync',"
)
old = """app.get('/api/continue-after-qr', auth, async (req,res) => {\n  const approved = await qrApprovalDetected();\n  if (!approved) return res.status(409).json({ok:false,approved:false,stage:getStatus().stage});\n  const started = await startAcquisition('manual-confirmed-tv-approval');\n  res.json({ok:true,approved:true,started,stage:getStatus().stage});\n});"""
new = """app.get('/api/continue-after-qr', auth, async (req,res) => {\n  let approved = await qrApprovalDetected();\n  if (!approved && page) {\n    await page.reload({ waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});\n    await page.waitForTimeout(5000).catch(() => {});\n    approved = await qrApprovalDetected();\n    console.log('Manual QR approval recheck after reload:', approved);\n  }\n  if (!approved) return res.status(409).json({ok:false,approved:false,stage:getStatus().stage});\n  const started = await startAcquisition('manual-confirmed-tv-approval');\n  res.json({ok:true,approved:true,started,stage:getStatus().stage});\n});"""
if old not in s:
    raise SystemExit('continue-after-qr block not found')
s = s.replace(old, new)
p.write_text(s)
PY

"$PWD/.chrome/opt/google/chrome/google-chrome" --version
./yt-dlp --version
