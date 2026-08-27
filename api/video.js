import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import sharp from 'sharp';
import ffmpegPath from 'ffmpeg-static';
import { contentBank } from '../content/content-bank.js';

function esc(s='') {
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
}

function svgFrame(item, line, index) {
  const accents = ['#9B5DE5','#00BBF9','#F15BB5','#00F5D4'];
  const accent = accents[index % accents.length];
  const sub = item.format.replaceAll('_', ' ').toUpperCase();
  return `<svg width="720" height="1280" viewBox="0 0 720 1280" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#090A0F"/><stop offset="55%" stop-color="#15182A"/><stop offset="100%" stop-color="#05060A"/></linearGradient>
      <radialGradient id="r" cx="50%" cy="38%" r="60%"><stop offset="0%" stop-color="${accent}" stop-opacity="0.38"/><stop offset="100%" stop-color="${accent}" stop-opacity="0"/></radialGradient>
    </defs>
    <rect width="720" height="1280" fill="url(#g)"/><rect width="720" height="1280" fill="url(#r)"/>
    <circle cx="110" cy="160" r="170" fill="${accent}" opacity="0.08"/><circle cx="650" cy="1110" r="260" fill="${accent}" opacity="0.07"/>
    <text x="360" y="145" fill="#fff" opacity="0.72" text-anchor="middle" font-family="Arial" font-size="24" letter-spacing="5">RUBY'S REALM</text>
    <text x="360" y="205" fill="${accent}" opacity="0.9" text-anchor="middle" font-family="Arial" font-size="18" letter-spacing="3">${esc(sub)}</text>
    <foreignObject x="54" y="350" width="612" height="520"><div xmlns="http://www.w3.org/1999/xhtml" style="height:520px;display:flex;align-items:center;justify-content:center;text-align:center;color:#fff;font-family:Arial,sans-serif;font-weight:900;font-size:76px;line-height:1.04;letter-spacing:-2px;text-shadow:0 8px 30px rgba(0,0,0,.6);padding:18px;box-sizing:border-box;">${esc(line)}</div></foreignObject>
    <rect x="110" y="1020" width="500" height="8" rx="4" fill="#fff" opacity="0.12"/><rect x="110" y="1020" width="${125*(index+1)}" height="8" rx="4" fill="${accent}"/>
    <text x="360" y="1115" fill="#fff" opacity="0.6" text-anchor="middle" font-family="Arial" font-size="21">RUBY'S REALM</text>
  </svg>`;
}

function run(args) {
  return new Promise((resolve, reject) => {
    const p = spawn(ffmpegPath, args, { stdio: ['ignore','ignore','pipe'] });
    let err = '';
    p.stderr.on('data', d => { err += d.toString(); });
    p.on('error', reject);
    p.on('exit', code => code === 0 ? resolve() : reject(new Error(`ffmpeg ${code}: ${err.slice(-1000)}`)));
  });
}

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') return res.status(405).end();
  const id = String(req.query?.id || '');
  const item = contentBank.find(x => x.id === id);
  if (!item) return res.status(404).json({ error: 'Unknown content id' });

  if (req.method === 'HEAD') {
    res.setHeader('Content-Type', 'video/mp4');
    res.setHeader('Cache-Control', 'public, max-age=86400, s-maxage=31536000, immutable');
    return res.status(200).end();
  }

  const dir = await fs.mkdtemp(path.join(os.tmpdir(), `rr-${id}-`));
  try {
    const frames = [];
    for (let i = 0; i < item.lines.length; i++) {
      const file = path.join(dir, `f${i}.png`);
      await sharp(Buffer.from(svgFrame(item, item.lines[i], i))).png().toFile(file);
      frames.push(file);
    }

    const output = path.join(dir, `${id}.mp4`);
    const inputs = frames.flatMap(f => ['-loop','1','-framerate','30','-t','2','-i',f]);
    const filter = frames.map((_,i) => `[${i}:v]scale=720:1280,setsar=1,format=yuv420p,trim=duration=2,setpts=PTS-STARTPTS[v${i}]`).join(';') + ';' + frames.map((_,i)=>`[v${i}]`).join('') + `concat=n=${frames.length}:v=1:a=0[v]`;
    await run(['-y', ...inputs, '-filter_complex', filter, '-map','[v]','-r','30','-c:v','libx264','-preset','ultrafast','-crf','25','-pix_fmt','yuv420p','-movflags','+faststart', output]);

    const video = await fs.readFile(output);
    res.setHeader('Content-Type','video/mp4');
    res.setHeader('Content-Length', String(video.length));
    res.setHeader('Cache-Control','public, max-age=86400, s-maxage=31536000, immutable');
    return res.status(200).send(video);
  } catch (error) {
    console.error('video render failed', error);
    return res.status(500).json({ error: 'Video render failed' });
  } finally {
    await fs.rm(dir, { recursive:true, force:true }).catch(()=>{});
  }
}
