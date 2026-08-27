import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import sharp from 'sharp';
import ffmpegPath from 'ffmpeg-static';
import { contentBank } from '../content/content-bank.js';

export const config = { maxDuration: 300 };

const WIDTH = 540;
const HEIGHT = 960;
const TARGET_SECONDS = 590; // 9:50, safely below TikTok/Buffer's 10-minute automation ceiling.
const FPS = 12;

function esc(s='') {
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
}

function svgFrame(item, line, lineIndex, storyIndex) {
  const accents = ['#9B5DE5','#00BBF9','#F15BB5','#00F5D4','#FEE440','#FF6B6B'];
  const accent = accents[(storyIndex + lineIndex) % accents.length];
  const sub = item.format.replaceAll('_', ' ').toUpperCase();
  const progress = Math.max(5, Math.round(((storyIndex + (lineIndex + 1) / item.lines.length) / contentBank.length) * 500));
  return `<svg width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#090A0F"/><stop offset="55%" stop-color="#15182A"/><stop offset="100%" stop-color="#05060A"/></linearGradient>
      <radialGradient id="r" cx="50%" cy="38%" r="65%"><stop offset="0%" stop-color="${accent}" stop-opacity="0.42"/><stop offset="100%" stop-color="${accent}" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="${WIDTH}" height="${HEIGHT}" fill="url(#g)"/><rect width="${WIDTH}" height="${HEIGHT}" fill="url(#r)"/>
    <circle cx="80" cy="110" r="130" fill="${accent}" opacity="0.08"/><circle cx="500" cy="835" r="190" fill="${accent}" opacity="0.07"/>
    <text x="270" y="100" fill="#fff" opacity="0.74" text-anchor="middle" font-family="Arial" font-size="21" letter-spacing="4">RUBY'S REALM</text>
    <text x="270" y="145" fill="${accent}" opacity="0.92" text-anchor="middle" font-family="Arial" font-size="14" letter-spacing="2">${esc(sub)} • STORY ${storyIndex + 1}</text>
    <foreignObject x="38" y="250" width="464" height="390"><div xmlns="http://www.w3.org/1999/xhtml" style="height:390px;display:flex;align-items:center;justify-content:center;text-align:center;color:#fff;font-family:Arial,sans-serif;font-weight:900;font-size:58px;line-height:1.04;letter-spacing:-1px;text-shadow:0 7px 26px rgba(0,0,0,.62);padding:12px;box-sizing:border-box;">${esc(line)}</div></foreignObject>
    <rect x="20" y="775" width="500" height="7" rx="4" fill="#fff" opacity="0.13"/><rect x="20" y="775" width="${progress}" height="7" rx="4" fill="${accent}"/>
    <text x="270" y="835" fill="#fff" opacity="0.58" text-anchor="middle" font-family="Arial" font-size="17">STAY TO THE END • NEW STORY EVERY FEW SECONDS</text>
  </svg>`;
}

function run(args) {
  return new Promise((resolve, reject) => {
    const p = spawn(ffmpegPath, args, { stdio: ['ignore','ignore','pipe'] });
    let err = '';
    p.stderr.on('data', d => { err += d.toString(); });
    p.on('error', reject);
    p.on('exit', code => code === 0 ? resolve() : reject(new Error(`ffmpeg ${code}: ${err.slice(-1400)}`)));
  });
}

function rotateBank(id) {
  const start = Math.max(0, contentBank.findIndex(x => x.id === id));
  return [...contentBank.slice(start), ...contentBank.slice(0, start)];
}

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') return res.status(405).end();
  const id = String(req.query?.id || '');
  const selected = contentBank.find(x => x.id === id);
  if (!selected) return res.status(404).json({ error: 'Unknown content id' });

  if (req.method === 'HEAD') {
    res.setHeader('Content-Type', 'video/mp4');
    res.setHeader('Cache-Control', 'public, max-age=86400, s-maxage=31536000, immutable');
    return res.status(200).end();
  }

  const dir = await fs.mkdtemp(path.join(os.tmpdir(), `rr-long-${id}-`));
  try {
    const ordered = rotateBank(id);
    const cards = [];

    for (let storyIndex = 0; storyIndex < ordered.length; storyIndex++) {
      const story = ordered[storyIndex];
      for (let lineIndex = 0; lineIndex < story.lines.length; lineIndex++) {
        cards.push({ story, line: story.lines[lineIndex], storyIndex, lineIndex });
      }
    }

    const secondsPerCard = TARGET_SECONDS / cards.length;
    const concatLines = [];

    for (let i = 0; i < cards.length; i++) {
      const card = cards[i];
      const file = path.join(dir, `f${String(i).padStart(3,'0')}.png`);
      await sharp(Buffer.from(svgFrame(card.story, card.line, card.lineIndex, card.storyIndex))).png({ compressionLevel: 5 }).toFile(file);
      concatLines.push(`file '${file.replaceAll("'", "'\\''")}'`);
      concatLines.push(`duration ${secondsPerCard.toFixed(6)}`);
    }

    // The concat demuxer needs the final file repeated for the last duration to be honored.
    const lastFile = path.join(dir, `f${String(cards.length - 1).padStart(3,'0')}.png`);
    concatLines.push(`file '${lastFile.replaceAll("'", "'\\''")}'`);

    const concatFile = path.join(dir, 'concat.txt');
    await fs.writeFile(concatFile, concatLines.join('\n'));

    const output = path.join(dir, `${id}.mp4`);
    await run([
      '-y',
      '-f','concat','-safe','0','-i',concatFile,
      '-vf',`scale=${WIDTH}:${HEIGHT}:flags=fast_bilinear,format=yuv420p`,
      '-r',String(FPS),
      '-t',String(TARGET_SECONDS),
      '-an',
      '-c:v','libx264','-preset','ultrafast','-crf','31',
      '-pix_fmt','yuv420p',
      '-movflags','+faststart',
      output
    ]);

    const video = await fs.readFile(output);
    res.setHeader('Content-Type','video/mp4');
    res.setHeader('Content-Length', String(video.length));
    res.setHeader('Cache-Control','public, max-age=86400, s-maxage=31536000, immutable');
    res.setHeader('X-Rubys-Realm-Duration', String(TARGET_SECONDS));
    return res.status(200).send(video);
  } catch (error) {
    console.error('long video render failed', error);
    return res.status(500).json({ error: 'Long video render failed' });
  } finally {
    await fs.rm(dir, { recursive:true, force:true }).catch(()=>{});
  }
}
