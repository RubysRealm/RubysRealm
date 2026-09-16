import express from 'express';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const app = express();
const PORT = Number(process.env.PORT || 10000);
const DESKTOP_TOKEN = String(process.env.DESKTOP_TOKEN || '').trim();
const W = Number(process.env.STREAM_WIDTH || 720);
const H = Number(process.env.STREAM_HEIGHT || 1280);
const SOURCE_DIR = '/tmp/rubyclips-source';

app.use(express.json({ limit: '64kb' }));
app.use(express.static('public'));

function desktopAuth(req, res, next) {
  const t = String(req.query.token || req.headers['x-desktop-token'] || '');
  if (!DESKTOP_TOKEN || t !== DESKTOP_TOKEN) return res.status(403).send('Bad desktop token');
  next();
}

function desktopCommand(args) {
  const p = spawn('xdotool', args, { env: { ...process.env, DISPLAY: ':99' }, stdio: 'ignore' });
  p.on('error', () => {});
}

function readStatus() {
  try {
    return JSON.parse(fs.readFileSync(path.join(SOURCE_DIR, 'status.json'), 'utf8'));
  } catch {
    return {
      stage: 'waiting_for_login',
      signedIn: false,
      downloading: false,
      readyParts: [],
      totalParts: Number(process.env.STORY_TOTAL_PARTS || 11),
      videoId: process.env.YOUTUBE_VIDEO_ID || '5-bO9NAhWbI'
    };
  }
}

app.get('/', (req, res) => {
  const s = readStatus();
  res.type('html').send(`<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><body style="background:#090a0f;color:#fff;font:18px system-ui;padding:28px"><h1>Rubradaclips YouTube Source</h1><p>Status: <b>${String(s.stage)}</b></p><p>Ready parts: ${(s.readyParts || []).length}/${s.totalParts || 11}</p></body>`);
});

app.get('/desktop', desktopAuth, (req, res) => res.sendFile(path.resolve('public/desktop.html')));
app.get('/api/desktop-frame', desktopAuth, (req, res) => {
  res.setHeader('Cache-Control', 'no-store, max-age=0');
  if (!fs.existsSync('/tmp/cloud-frame.jpg')) return res.status(503).send('Cloud desktop frame not ready');
  res.sendFile('/tmp/cloud-frame.jpg');
});
app.post('/api/desktop-click', desktopAuth, (req, res) => {
  const x = Math.max(0, Math.min(W - 1, Math.round(Number(req.body?.x) || 0)));
  const y = Math.max(0, Math.min(H - 1, Math.round(Number(req.body?.y) || 0)));
  desktopCommand(['mousemove', String(x), String(y), 'click', '1']);
  res.json({ ok: true, x, y });
});
app.post('/api/desktop-key', desktopAuth, (req, res) => {
  const allowed = new Set(['Return','Tab','Escape','BackSpace','Up','Down','Left','Right','space','ctrl+l']);
  const key = String(req.body?.key || '');
  if (!allowed.has(key)) return res.status(400).json({ ok: false });
  desktopCommand(['key', key]);
  res.json({ ok: true });
});
app.post('/api/desktop-type', desktopAuth, (req, res) => {
  const text = String(req.body?.text || '').slice(0, 500);
  desktopCommand(['type', '--delay', '20', '--clearmodifiers', text]);
  res.json({ ok: true });
});

app.get('/api/state', (req, res) => res.json(readStatus()));

app.get('/source/:name', (req, res) => {
  const name = path.basename(String(req.params.name || ''));
  if (!/^source-part-\d{2}\.mp4$/.test(name) && name !== 'source-manifest.json') return res.status(404).end();
  const file = path.join(SOURCE_DIR, name);
  if (!fs.existsSync(file)) return res.status(404).end();
  res.setHeader('Cache-Control', 'no-store');
  res.sendFile(file);
});

app.get('/healthz', (req, res) => res.json({ ok: true, service: 'rubyclips-youtube-phone' }));

app.listen(PORT, '0.0.0.0', () => console.log(`Rubradaclips YouTube phone on :${PORT}`));
