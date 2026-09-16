import express from 'express';
import { chromium } from 'playwright-core';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import ffmpegPath from 'ffmpeg-static';

const PORT = Number(process.env.PORT || 10000);
const TOKEN = String(process.env.DESKTOP_TOKEN || '').trim();
const VIDEO_ID = process.env.YOUTUBE_VIDEO_ID || '5-bO9NAhWbI';
const VIDEO_URL = process.env.YOUTUBE_SOURCE_URL || `https://www.youtube.com/watch?v=${VIDEO_ID}`;
const TOTAL_PARTS = Number(process.env.STORY_TOTAL_PARTS || 11);
const SOURCE_DURATION = Number(process.env.SOURCE_DURATION_SECONDS || 6372);
const SEGMENT_SECONDS = Number(process.env.SEGMENT_SECONDS || 595);
const PROFILE = '/tmp/youtube-browser';
const SOURCE_DIR = '/tmp/rubyclips-source';
const STATUS = path.join(SOURCE_DIR, 'status.json');
const FULL = path.join(SOURCE_DIR, 'full.mp4');
const CHROME = process.env.CHROME_PATH || path.resolve('.chrome/opt/google/chrome/google-chrome');
const YTDLP = process.env.YTDLP_PATH || path.resolve('yt-dlp');
const TV_URL = 'https://www.youtube.com/tv';
const TV_UA = 'Mozilla/5.0 (SMART-TV; LINUX; Tizen 7.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/2.2 Chrome/94.0.4606.31 TV Safari/537.36';

fs.mkdirSync(PROFILE, { recursive: true });
fs.mkdirSync(SOURCE_DIR, { recursive: true });

let context = null;
let page = null;
let acquisitionStarted = false;

function readyParts() {
  const out = [];
  for (let i = 1; i <= TOTAL_PARTS; i++) {
    const f = path.join(SOURCE_DIR, `source-part-${String(i).padStart(2, '0')}.mp4`);
    if (fs.existsSync(f) && fs.statSync(f).size > 250000) out.push(i);
  }
  return out;
}

function setStatus(extra = {}) {
  let prior = {};
  try { prior = JSON.parse(fs.readFileSync(STATUS, 'utf8')); } catch {}
  const next = {
    stage: 'starting', signedIn: false, downloading: false,
    videoId: VIDEO_ID, sourceUrl: VIDEO_URL, totalParts: TOTAL_PARTS,
    sourceDurationSeconds: SOURCE_DURATION, segmentSeconds: SEGMENT_SECONDS,
    ...prior, ...extra, readyParts: readyParts(), updatedAt: new Date().toISOString()
  };
  fs.writeFileSync(STATUS, JSON.stringify(next, null, 2));
  return next;
}

function getStatus() {
  try { return JSON.parse(fs.readFileSync(STATUS, 'utf8')); }
  catch { return setStatus(); }
}

function run(cmd, args) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: ['ignore', 'inherit', 'inherit'] });
    p.once('error', reject);
    p.once('exit', c => c === 0 ? resolve() : reject(new Error(`${path.basename(cmd)} exited ${c}`)));
  });
}

async function qrApprovalDetected() {
  if (!context || !page) return false;
  try {
    const body = (await page.locator('body').innerText({ timeout: 2500 }).catch(() => '')).replace(/\s+/g, ' ').trim();
    const pending = /scan qr code|yt\.be\/activate|enter the code|sign in with (your )?phone/i.test(body);
    const signedInUi = /\bhome\b|subscriptions|library|\byou\b|your videos|watch history/i.test(body);
    const cookies = await context.cookies(['https://www.youtube.com/', 'https://accounts.google.com/']).catch(() => []);
    const cookieNames = [...new Set(cookies.map(c => c.name))].sort();
    const normalAuthNames = new Set(['SID','SAPISID','__Secure-1PSID','__Secure-3PSID','__Secure-1PAPISID','__Secure-3PAPISID']);
    const hasNormalAuth = cookies.some(c => normalAuthNames.has(c.name) && c.value);
    if (!pending && (signedInUi || hasNormalAuth)) {
      let localKeys = [];
      try { localKeys = await page.evaluate(() => Object.keys(localStorage)); } catch {}
      console.log('YouTube TV approval detected. URL:', page.url());
      console.log('YouTube cookie names:', cookieNames.join(', '));
      console.log('YouTube localStorage keys:', localKeys.join(', '));
      return true;
    }
    return false;
  } catch (e) {
    console.log('QR approval check:', String(e?.message || e).slice(0, 300));
    return false;
  }
}

async function clickVisibleText(regex) {
  const loc = page.getByText(regex).first();
  if (!await loc.count()) return false;
  if (!await loc.isVisible({ timeout: 1500 }).catch(() => false)) return false;
  await loc.click({ timeout: 5000 }).catch(() => {});
  return true;
}

async function prepareTvQr() {
  setStatus({ stage: 'opening_youtube_tv', signedIn: false, downloading: false, error: null });
  await page.goto(TV_URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await page.waitForTimeout(7000);

  let body = await page.locator('body').innerText().catch(() => '');
  console.log('YouTube TV initial:', body.slice(0, 900).replace(/\s+/g, ' '));

  let clicked = await clickVisibleText(/^Sign in$/i);
  if (!clicked) clicked = await clickVisibleText(/sign in/i);
  if (!clicked) {
    await page.keyboard.press('ArrowLeft').catch(() => {});
    await page.waitForTimeout(800);
    for (let i = 0; i < 7; i++) {
      body = await page.locator('body').innerText().catch(() => '');
      if (/sign in/i.test(body)) break;
      await page.keyboard.press('ArrowUp').catch(() => {});
      await page.waitForTimeout(250);
    }
    await page.keyboard.press('Enter').catch(() => {});
  }

  await page.waitForTimeout(3500);
  await clickVisibleText(/sign in with (your )?phone/i);
  await page.waitForTimeout(5000);
  body = await page.locator('body').innerText().catch(() => '');
  console.log('YouTube TV QR stage:', body.slice(0, 1200).replace(/\s+/g, ' '));
  setStatus({ stage: 'scan_youtube_qr', signedIn: false, downloading: false, error: null });
}

function sourcePartPath(part) {
  return path.join(SOURCE_DIR, `source-part-${String(part).padStart(2, '0')}.mp4`);
}

async function downloadPartOneFirst() {
  const finalOut = sourcePartPath(1);
  if (fs.existsSync(finalOut) && fs.statSync(finalOut).size > 250000) return;
  const template = path.join(SOURCE_DIR, 'part1-fast.%(ext)s');
  setStatus({ stage: 'downloading_part_1', signedIn: true, downloading: true });
  await run(YTDLP, [
    '--ffmpeg-location', ffmpegPath,
    '--cookies-from-browser', `chrome+basictext:${PROFILE}`,
    '--extractor-args', 'youtube:player_client=web,tv',
    '--no-playlist', '--retries', '20', '--fragment-retries', '20', '--concurrent-fragments', '2',
    '--download-sections', `*0-${SEGMENT_SECONDS}`,
    '-f', 'bv*[height<=720][vcodec^=avc1]+ba[acodec^=mp4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]',
    '--merge-output-format', 'mp4', '--remux-video', 'mp4',
    '-o', template, VIDEO_URL
  ]);
  const candidates = fs.readdirSync(SOURCE_DIR)
    .filter(x => /^part1-fast\.(mp4|mkv|webm|mov)$/i.test(x))
    .map(x => path.join(SOURCE_DIR, x))
    .sort((a,b) => fs.statSync(b).size - fs.statSync(a).size);
  if (!candidates.length) throw new Error('Fast Part 1 download did not create a media file');
  const src = candidates[0];
  if (src !== finalOut) {
    if (/\.mp4$/i.test(src)) fs.renameSync(src, finalOut);
    else {
      await run(ffmpegPath, ['-y','-hide_banner','-loglevel','error','-i',src,'-c','copy','-movflags','+faststart',finalOut]);
      try { fs.unlinkSync(src); } catch {}
    }
  }
  if (!fs.existsSync(finalOut) || fs.statSync(finalOut).size < 250000) throw new Error('Fast Part 1 file is unexpectedly small');
  setStatus({ stage: 'part_1_ready', signedIn: true, downloading: true });
  console.log('Rubradaclips source Part 1 ready:', fs.statSync(finalOut).size, 'bytes');
}

async function acquire() {
  setStatus({ stage: 'login_confirmed', signedIn: true, downloading: false, error: null });

  // Give the TV app a moment to persist its authorized session before closing Chrome.
  await page?.waitForTimeout(2500).catch(() => {});
  if (context) {
    await context.close().catch(() => {});
    context = null;
    page = null;
    await new Promise(r => setTimeout(r, 1200));
  }

  // Prepare the first TikTok part immediately instead of waiting for the entire 106-minute source.
  await downloadPartOneFirst();

  setStatus({ stage: 'downloading_full_source', signedIn: true, downloading: true });
  await run(YTDLP, [
    '--ffmpeg-location', ffmpegPath,
    '--cookies-from-browser', `chrome+basictext:${PROFILE}`,
    '--extractor-args', 'youtube:player_client=web,tv',
    '--no-playlist', '--retries', '20', '--fragment-retries', '20', '--concurrent-fragments', '2',
    '-f', 'bv*[height<=720][vcodec^=avc1]+ba[acodec^=mp4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]',
    '--merge-output-format', 'mp4', '--remux-video', 'mp4',
    '-o', path.join(SOURCE_DIR, 'full.%(ext)s'), VIDEO_URL
  ]);

  const files = fs.readdirSync(SOURCE_DIR)
    .filter(x => /^full\.(mp4|mkv|webm|mov)$/i.test(x))
    .map(x => path.join(SOURCE_DIR, x));
  if (!files.length) throw new Error('No downloaded source file was created');
  const src = files.sort((a,b) => fs.statSync(b).size - fs.statSync(a).size)[0];
  if (src !== FULL) await run(ffmpegPath, ['-y','-hide_banner','-loglevel','error','-i',src,'-c','copy','-movflags','+faststart',FULL]);
  if (!fs.existsSync(FULL) || fs.statSync(FULL).size < 1000000) throw new Error('Downloaded source is unexpectedly small');

  setStatus({ stage: 'splitting_source', signedIn: true, downloading: true });
  for (let part = 2; part <= TOTAL_PARTS; part++) {
    const out = sourcePartPath(part);
    const start = (part - 1) * SEGMENT_SECONDS;
    const len = Math.min(SEGMENT_SECONDS, Math.max(0, SOURCE_DURATION - start));
    if (len <= 0.5) break;
    if (!(fs.existsSync(out) && fs.statSync(out).size > 250000)) {
      const tmp = out + '.tmp.mp4';
      try { fs.unlinkSync(tmp); } catch {}
      await run(ffmpegPath, ['-y','-hide_banner','-loglevel','error','-ss',String(start),'-i',FULL,'-t',String(len),'-map','0:v:0','-map','0:a:0?','-c','copy','-avoid_negative_ts','make_zero','-movflags','+faststart',tmp]);
      fs.renameSync(tmp, out);
    }
    setStatus({ stage: `part_${part}_ready`, signedIn: true, downloading: true });
  }

  fs.writeFileSync(path.join(SOURCE_DIR, 'source-manifest.json'), JSON.stringify({
    sourceProvider: 'youtube-tv-qr-auth', sourceChannel: '@muffindrama-uvu', videoId: VIDEO_ID,
    sourceUrl: VIDEO_URL, durationSeconds: SOURCE_DURATION, totalParts: TOTAL_PARTS,
    segmentSeconds: SEGMENT_SECONDS, sessionExported: false, createdAt: new Date().toISOString()
  }, null, 2));
  setStatus({ stage: 'ready', signedIn: true, downloading: false, error: null });
}

async function startAcquisition(reason = 'automatic') {
  if (acquisitionStarted || getStatus().stage === 'ready') return false;
  acquisitionStarted = true;
  console.log('Starting Rubradaclips acquisition:', reason);
  acquire().catch(e => {
    console.error('Rubradaclips acquisition failed:', e);
    setStatus({ stage: 'error', signedIn: true, downloading: false, error: String(e?.message || e) });
    acquisitionStarted = false;
  });
  return true;
}

const app = express();
app.use(express.json({ limit: '64kb' }));
app.use(express.static('public'));

function auth(req, res, next) {
  const t = String(req.query.token || req.headers['x-desktop-token'] || '');
  if (!TOKEN || t !== TOKEN) return res.status(403).send('Bad desktop token');
  next();
}

app.get('/', (req,res) => {
  const s = getStatus();
  res.type('html').send(`<meta name="viewport" content="width=device-width,initial-scale=1"><body style="background:#090a0f;color:#fff;font:18px system-ui;padding:28px"><h1>Rubradaclips YouTube Source</h1><p>Status: <b>${s.stage}</b></p><p>Ready parts: ${(s.readyParts||[]).length}/${s.totalParts}</p></body>`);
});
app.get('/desktop', auth, (req,res) => res.sendFile(path.resolve('public/desktop.html')));
app.get('/api/desktop-frame', auth, async (req,res) => {
  if (!page) return res.status(503).send('Browser is no longer needed; check source status.');
  try {
    const b = await page.screenshot({ type: 'jpeg', quality: 68 });
    res.setHeader('Content-Type','image/jpeg');
    res.setHeader('Cache-Control','no-store');
    res.end(b);
  } catch(e) { res.status(503).send(e.message); }
});
app.post('/api/desktop-click', auth, async (req,res) => {
  if (!page) return res.status(503).json({ok:false,error:'browser unavailable'});
  try { await page.mouse.click(Math.max(0,Math.min(1279,Number(req.body?.x)||0)),Math.max(0,Math.min(719,Number(req.body?.y)||0))); res.json({ok:true}); }
  catch(e){res.status(500).json({ok:false,error:e.message});}
});
app.post('/api/desktop-key', auth, async (req,res) => {
  if (!page) return res.status(503).json({ok:false,error:'browser unavailable'});
  const m={Return:'Enter',Tab:'Tab',Escape:'Escape',BackSpace:'Backspace',Up:'ArrowUp',Down:'ArrowDown',Left:'ArrowLeft',Right:'ArrowRight',space:'Space'};
  const k=m[String(req.body?.key||'')]; if(!k)return res.status(400).json({ok:false});
  try { await page.keyboard.press(k); res.json({ok:true}); } catch(e){res.status(500).json({ok:false,error:e.message});}
});
app.get('/api/continue-after-qr', auth, async (req,res) => {
  const approved = await qrApprovalDetected();
  if (!approved) return res.status(409).json({ok:false,approved:false,stage:getStatus().stage});
  const started = await startAcquisition('manual-confirmed-tv-approval');
  res.json({ok:true,approved:true,started,stage:getStatus().stage});
});
app.get('/api/state',(req,res)=>res.json(getStatus()));
app.get('/healthz',(req,res)=>res.json({ok:true,service:'rubyclips-youtube-phone',browser:!!page,stage:getStatus().stage}));
app.get('/source/:name',(req,res)=>{
  const n=path.basename(String(req.params.name||''));
  if(!/^source-part-\d{2}\.mp4$/.test(n)&&n!=='source-manifest.json')return res.status(404).end();
  const f=path.join(SOURCE_DIR,n); if(!fs.existsSync(f))return res.status(404).end();
  res.setHeader('Cache-Control','no-store'); res.sendFile(f);
});
app.listen(PORT,'0.0.0.0',()=>console.log(`Rubradaclips YouTube QR host listening on ${PORT}`));

async function boot() {
  setStatus({stage:'starting_browser',signedIn:false,downloading:false,error:null});
  try {
    context = await chromium.launchPersistentContext(PROFILE, {
      headless: true,
      executablePath: CHROME,
      userAgent: TV_UA,
      viewport: { width: 1280, height: 720 },
      args: [
        '--no-sandbox','--disable-dev-shm-usage','--password-store=basic','--no-first-run','--no-default-browser-check',
        '--disable-features=TranslateUI','--disable-background-networking','--disable-component-update','--disable-sync',
        '--disable-extensions','--disable-renderer-backgrounding','--renderer-process-limit=1'
      ]
    });
    page = context.pages()[0] || await context.newPage();
    await prepareTvQr();

    let checking = false;
    const timer = setInterval(async()=>{
      if (checking || acquisitionStarted || getStatus().stage === 'ready') return;
      checking = true;
      try {
        if (await qrApprovalDetected()) {
          clearInterval(timer);
          await startAcquisition('youtube-tv-qr-approved');
        }
      } finally { checking = false; }
    },4000);
    timer.unref();
  } catch(e) {
    console.error('browser startup failed',e);
    setStatus({stage:'browser_error',error:String(e?.message||e)});
  }
}

boot();
