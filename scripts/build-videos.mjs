import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import sharp from 'sharp';
import ffmpegPath from 'ffmpeg-static';
import { contentBank } from '../content/content-bank.js';

const ROOT = process.cwd();
const OUT = path.join(ROOT, 'public', 'videos');
const TMP = path.join(ROOT, '.video-build');

await fs.mkdir(OUT, { recursive: true });
await fs.mkdir(TMP, { recursive: true });

function esc(s='') {
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
}

function svgFrame(line, index, format) {
  const accents = ['#9B5DE5','#00BBF9','#F15BB5','#00F5D4'];
  const accent = accents[index % accents.length];
  const sub = format.replaceAll('_', ' ').toUpperCase();
  return `
  <svg width="720" height="1280" viewBox="0 0 720 1280" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#090A0F"/>
        <stop offset="55%" stop-color="#15182A"/>
        <stop offset="100%" stop-color="#05060A"/>
      </linearGradient>
      <radialGradient id="r" cx="50%" cy="38%" r="60%">
        <stop offset="0%" stop-color="${accent}" stop-opacity="0.38"/>
        <stop offset="100%" stop-color="${accent}" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect width="720" height="1280" fill="url(#g)"/>
    <rect width="720" height="1280" fill="url(#r)"/>
    <circle cx="110" cy="160" r="170" fill="${accent}" opacity="0.08"/>
    <circle cx="650" cy="1110" r="260" fill="${accent}" opacity="0.07"/>
    <text x="360" y="145" fill="#FFFFFF" opacity="0.72" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="24" letter-spacing="5">RUBY'S REALM</text>
    <text x="360" y="205" fill="${accent}" opacity="0.9" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="18" letter-spacing="3">${esc(sub)}</text>
    <foreignObject x="54" y="360" width="612" height="500">
      <div xmlns="http://www.w3.org/1999/xhtml" style="height:500px;display:flex;align-items:center;justify-content:center;text-align:center;color:#fff;font-family:Arial,Helvetica,sans-serif;font-weight:900;font-size:78px;line-height:1.04;letter-spacing:-2px;text-shadow:0 8px 30px rgba(0,0,0,.6);padding:18px;box-sizing:border-box;">${esc(line)}</div>
    </foreignObject>
    <rect x="110" y="1020" width="500" height="8" rx="4" fill="#FFFFFF" opacity="0.12"/>
    <rect x="110" y="1020" width="${125 * (index + 1)}" height="8" rx="4" fill="${accent}"/>
    <text x="360" y="1115" fill="#FFFFFF" opacity="0.6" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="21">@rubysrealm</text>
  </svg>`;
}

function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: 'inherit' });
    p.on('exit', code => code === 0 ? resolve() : reject(new Error(`ffmpeg exited ${code}`)));
    p.on('error', reject);
  });
}

for (const item of contentBank) {
  const frames = [];
  for (let i = 0; i < item.lines.length; i++) {
    const frame = path.join(TMP, `${item.id}-${i}.png`);
    await sharp(Buffer.from(svgFrame(item.lines[i], i, item.format))).png().toFile(frame);
    frames.push(frame);
  }

  const output = path.join(OUT, `${item.id}.mp4`);
  const inputArgs = frames.flatMap(f => ['-loop', '1', '-t', '2', '-i', f]);
  const filter = frames.map((_, i) => `[${i}:v]scale=720:1280,zoompan=z='min(zoom+0.0012,1.08)':d=60:s=720x1280:fps=30,setsar=1[v${i}]`).join(';') + ';' + frames.map((_, i) => `[v${i}]`).join('') + `concat=n=${frames.length}:v=1:a=0[v]`;

  await run(ffmpegPath, [
    '-y', ...inputArgs,
    '-filter_complex', filter,
    '-map', '[v]',
    '-c:v', 'libx264',
    '-preset', 'veryfast',
    '-crf', '24',
    '-pix_fmt', 'yuv420p',
    '-movflags', '+faststart',
    output
  ]);
}

await fs.rm(TMP, { recursive: true, force: true });
console.log(`Built ${contentBank.length} Ruby's Realm videos.`);
