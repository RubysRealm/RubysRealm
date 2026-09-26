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
const GUEST_PROFILE = '/tmp/youtube-guest-browser';
const GUEST_COOKIE_FILE = '/tmp/rubyclips-youtube-guest.cookies.txt';
const SOURCE_DIR = '/tmp/rubyclips-source';
const STATUS = path.join(SOURCE_DIR, 'status.json');
const FULL = path.join(SOURCE_DIR, 'full.mp4');
const CHROME = process.env.CHROME_PATH || path.resolve('.chrome/opt/google/chrome/google-chrome');
const YTDLP = process.env.YTDLP_PATH || path.resolve('yt-dlp');
const TV_URL = 'https://www.youtube.com/tv';
const TV_UA = 'Mozilla/5.0 (SMART-TV; LINUX; Tizen 7.0) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/2.2 Chrome/94.0.4606.31 TV Safari/537.36';


const AUTO_SOURCE_APIS = [
  'https://tube.rklab.co.in',
  'https://invidious.nerdvpn.de',
  'https://yt.chocolatemoo53.com',
  'https://invidious.tiekoetter.com',
  'https://inv.nadeko.net'
];
const AUTO_COBALT_APIS = [
  'https://cobalt-api.meowing.de/',
  'https://capi.3kh0.net/'
];

async function fetchJson(url, opts = {}, timeoutMs = 25000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const r = await fetch(url, {
      ...opts,
      signal: controller.signal,
      headers: {
        'user-agent': 'Mozilla/5.0 Chrome/151 Safari/537.36',
        'accept': 'application/json',
        ...(opts.headers || {})
      }
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${(await r.text()).slice(0,240)}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}


function netscapeCookieLine(c) {
  const domain = String(c.domain || '.youtube.com');
  const includeSubdomains = domain.startsWith('.') ? 'TRUE' : 'FALSE';
  const cookiePath = String(c.path || '/');
  const secure = c.secure ? 'TRUE' : 'FALSE';
  const expires = Number.isFinite(Number(c.expires)) && Number(c.expires) > 0 ? Math.floor(Number(c.expires)) : 0;
  return [domain, includeSubdomains, cookiePath, secure, expires, String(c.name || ''), String(c.value || '')].join('\t');
}

async function exportYouTubeCookies(browserContext, dest = GUEST_COOKIE_FILE) {
  const cookies = await browserContext.cookies([
    'https://www.youtube.com/',
    'https://youtube.com/',
    'https://accounts.google.com/'
  ]);
  if (!cookies.length) throw new Error('Browser session produced no YouTube cookies.');
  const lines = ['# Netscape HTTP Cookie File', '# Generated from the live Rubaradaclips browser session.'];
  for (const c of cookies) {
    if (!c.name || !c.value) continue;
    lines.push(netscapeCookieLine(c));
  }
  fs.writeFileSync(dest, lines.join('\n') + '\n', { mode: 0o600 });
  console.log('Exported YouTube browser cookies:', cookies.map(c => c.name).join(', '));
  return dest;
}

let guestCookiePromise = null;

async function prepareGuestCookiesOnce() {
  if (fs.existsSync(GUEST_COOKIE_FILE) && fs.statSync(GUEST_COOKIE_FILE).size > 100) {
    return GUEST_COOKIE_FILE;
  }
  if (guestCookiePromise) return await guestCookiePromise;
  guestCookiePromise = prepareGuestCookies();
  try {
    return await guestCookiePromise;
  } finally {
    guestCookiePromise = null;
  }
}

async function prepareGuestCookies() {
  let guestContext = null;
  try {
    fs.mkdirSync(GUEST_PROFILE, { recursive: true });
    guestContext = await chromium.launchPersistentContext(GUEST_PROFILE, {
      headless: true,
      executablePath: CHROME,
      userAgent: TV_UA,
      viewport: { width: 1280, height: 720 },
      args: [
        '--no-sandbox','--disable-dev-shm-usage','--password-store=basic','--no-first-run','--no-default-browser-check',
        '--disable-features=TranslateUI','--disable-background-networking','--disable-component-update','--disable-sync',
        '--disable-extensions','--disable-renderer-backgrounding','--renderer-process-limit=1',
        '--disable-gpu','--no-zygote','--single-process','--disable-software-rasterizer',
        '--disable-background-timer-throttling','--disable-backgrounding-occluded-windows',
        '--disable-breakpad','--disable-crash-reporter','--mute-audio'
      ]
    });
    const guestPage = guestContext.pages()[0] || await guestContext.newPage();
    await guestPage.goto(TV_URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await guestPage.waitForTimeout(5000);

    const clickText = async regex => {
      const loc = guestPage.getByText(regex);
      const count = await loc.count().catch(() => 0);
      for (let i = 0; i < count; i++) {
        const candidate = loc.nth(i);
        if (!await candidate.isVisible({ timeout: 1200 }).catch(() => false)) continue;
        try {
          await candidate.click({ timeout: 5000, force: true });
          return true;
        } catch {}
      }
      return false;
    };

    let body = (await guestPage.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ');
    console.log('YouTube guest bootstrap initial:', body.slice(0, 700));

    await clickText(/get started/i);
    await guestPage.waitForTimeout(2200);
    body = (await guestPage.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ');

    if (/watch as guest/i.test(body)) {
      let guestClicked = await clickText(/watch as guest/i);
      if (!guestClicked) {
        // YouTube TV sometimes renders the choices as non-standard focusable
        // elements. Walk the focus ring until "Watch as guest" is selected.
        for (let i = 0; i < 8 && !guestClicked; i++) {
          const active = await guestPage.evaluate(() => document.activeElement?.textContent || '').catch(() => '');
          if (/watch as guest/i.test(active)) {
            await guestPage.keyboard.press('Enter').catch(() => {});
            guestClicked = true;
            break;
          }
          await guestPage.keyboard.press('ArrowDown').catch(() => {});
          await guestPage.waitForTimeout(250);
        }
      }
      await guestPage.waitForTimeout(3500);
    }

    body = (await guestPage.locator('body').innerText().catch(() => '')).replace(/\s+/g, ' ');
    console.log('YouTube guest bootstrap final:', body.slice(0, 900));
    if (/scan qr code|yt\.be\/activate|sign in with (your )?phone/i.test(body) && !/home|subscriptions|library|search/i.test(body)) {
      throw new Error('YouTube TV guest mode did not activate.');
    }
    return await exportYouTubeCookies(guestContext);
  } finally {
    if (guestContext) await guestContext.close().catch(() => {});
  }
}


function normalizeGoogleVideoUrl(raw) {
  try {
    const u = new URL(raw);
    for (const k of ['range','rn','rbuf','sq','ump','alr','cpn']) u.searchParams.delete(k);
    return u.href;
  } catch {
    return raw;
  }
}

function youtubeItagKind(url) {
  try {
    const u = new URL(url);
    const itag = Number(u.searchParams.get('itag') || 0);
    const mime = String(u.searchParams.get('mime') || '').toLowerCase();
    if (itag === 18 || itag === 22) return 'muxed';
    if (mime.startsWith('audio/')) return 'audio';
    if (mime.startsWith('video/')) return 'video';
    if ([139,140,141,249,250,251].includes(itag)) return 'audio';
    if ([133,134,135,136,137,160,242,243,244,247,248,264,266,278,298,299,302,303,308,313,315,394,395,396,397,398,399,400,401].includes(itag)) return 'video';
    return 'unknown';
  } catch {
    return 'unknown';
  }
}

async function buildBrowserInterceptCut(videoId, start, duration) {
  const profile = path.join('/tmp', 'rubyclips-intercept-' + Date.now());
  let browserContext = null;
  try {
    browserContext = await chromium.launchPersistentContext(profile, {
      headless: true,
      executablePath: CHROME,
      viewport: { width: 1280, height: 720 },
      userAgent: TV_UA,
      extraHTTPHeaders: {
        'Referer': 'https://www.youtube.com/tv',
        'Origin': 'https://www.youtube.com'
      },
      args: [
        '--no-sandbox','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check',
        '--disable-gpu','--no-zygote','--single-process','--disable-software-rasterizer',
        '--disable-background-networking','--disable-component-update','--disable-sync',
        '--disable-extensions','--disable-renderer-backgrounding','--renderer-process-limit=1',
        '--mute-audio','--autoplay-policy=no-user-gesture-required'
      ]
    });

    const urls = [];
    browserContext.on('request', req => {
      const raw = req.url();
      if (!/googlevideo\.com\/videoplayback/i.test(raw)) return;
      const clean = normalizeGoogleVideoUrl(raw);
      if (!urls.includes(clean)) {
        urls.push(clean);
        const kind = youtubeItagKind(clean);
        let itag = '';
        try { itag = new URL(clean).searchParams.get('itag') || ''; } catch {}
        console.log('Captured YouTube browser media URL', {kind, itag});
      }
    });

    const page = browserContext.pages()[0] || await browserContext.newPage();

    const tryText = async regex => {
      const loc = page.getByText(regex);
      const count = await loc.count().catch(() => 0);
      for (let i = 0; i < count; i++) {
        const x = loc.nth(i);
        if (!await x.isVisible({timeout:800}).catch(() => false)) continue;
        if (await x.click({timeout:2500,force:true}).then(()=>true).catch(()=>false)) return true;
      }
      return false;
    };

    await page.goto(TV_URL, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await page.waitForTimeout(3500);
    let tvBody = (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g,' ');
    console.log('YouTube TV media capture initial:', tvBody.slice(0,900));

    let started = await tryText(/get started/i);
    if (!started) await page.keyboard.press('Enter').catch(() => {});
    await page.waitForTimeout(1800);
    tvBody = (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g,' ');
    if (/get started/i.test(tvBody)) {
      await page.keyboard.press('Enter').catch(() => {});
      await page.waitForTimeout(1800);
      tvBody = (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g,' ');
    }

    if (/watch as guest/i.test(tvBody)) {
      let guest = await tryText(/watch as guest/i);
      if (!guest) {
        for (let i = 0; i < 3; i++) {
          await page.keyboard.press('ArrowDown').catch(() => {});
          await page.waitForTimeout(250);
        }
        await page.keyboard.press('Enter').catch(() => {});
      }
      await page.waitForTimeout(3500);
    }

    tvBody = (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g,' ');
    console.log('YouTube TV media capture guest state:', tvBody.slice(0,1000));

    const tvWatch = TV_URL + '#/watch?v=' + encodeURIComponent(videoId);
    await page.goto(tvWatch, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await page.waitForTimeout(2500);
    await page.keyboard.press('Enter').catch(() => {});
    await page.waitForTimeout(1200);

    for (let i = 0; i < 16; i++) {
      await page.waitForTimeout(750);
      const kinds = new Set(urls.map(youtubeItagKind));
      if (kinds.has('muxed') || (kinds.has('video') && kinds.has('audio'))) break;
    }

    const muxed = urls.find(x => youtubeItagKind(x) === 'muxed');
    const video = urls.find(x => youtubeItagKind(x) === 'video');
    const audio = urls.find(x => youtubeItagKind(x) === 'audio');
    if (!muxed && !(video && audio)) {
      const body = (await page.locator('body').innerText().catch(() => '')).replace(/\s+/g,' ').slice(0,900);
      throw new Error('Browser did not expose usable YouTube media streams. Page: ' + body);
    }

    const out = path.join('/tmp', 'rubyclips-intercept-' + videoId + '-' + Math.round(start) + '-' + Date.now() + '.mp4');
    if (muxed) {
      await run(ffmpegPath, [
        '-y','-hide_banner','-loglevel','warning',
        '-rw_timeout','30000000','-reconnect','1','-reconnect_streamed','1','-reconnect_delay_max','5',
        '-ss',String(start),'-i',muxed,'-t',String(duration),
        '-map','0:v:0','-map','0:a:0?',
        '-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',out
      ]);
    } else {
      await run(ffmpegPath, [
        '-y','-hide_banner','-loglevel','warning',
        '-rw_timeout','30000000','-reconnect','1','-reconnect_streamed','1','-reconnect_delay_max','5',
        '-ss',String(start),'-i',video,'-ss',String(start),'-i',audio,'-t',String(duration),
        '-map','0:v:0','-map','1:a:0',
        '-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p',
        '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',out
      ]);
    }
    if (!fs.existsSync(out) || fs.statSync(out).size < 250000) {
      throw new Error('Browser-intercept source cut was unexpectedly small.');
    }
    return { out, source: 'youtube-browser-media-intercept', title: '' };
  } finally {
    if (browserContext) await browserContext.close().catch(() => {});
    try { fs.rmSync(profile, {recursive:true, force:true}); } catch {}
  }
}

async function buildBrowserSessionCut(videoId, start, duration) {
  const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
  try {
    return await buildBrowserInterceptCut(videoId, start, duration);
  } catch (interceptError) {
    console.warn('Browser media interception failed; trying cookie/yt-dlp path:', String(interceptError?.message || interceptError).slice(0,1200));
  }
  const cookieFile = await prepareGuestCookiesOnce();
  const out = path.join('/tmp', `rubyclips-browser-${videoId}-${Math.round(start)}-${Date.now()}.mp4`);
  const template = out.replace(/\.mp4$/i, '.%(ext)s');
  const end = start + duration;

  const args = [
    '--ffmpeg-location', ffmpegPath,
    '--cookies', cookieFile,
    '--no-playlist',
    '--no-progress',
    '--retries', '20',
    '--fragment-retries', '20',
    '--retry-sleep', 'fragment:2',
    '--concurrent-fragments', '2',
    '--js-runtimes', 'node',
    '--remote-components', 'ejs:github',
    '--extractor-args', 'youtube:player_client=tv,web_safari,web;formats=missing_pot,duplicate',
    '--add-header', 'Referer:https://www.youtube.com/',
    '--add-header', 'Origin:https://www.youtube.com',
    '--download-sections', `*${start.toFixed(3)}-${end.toFixed(3)}`,
    '-f', 'bv*[height<=720][vcodec^=avc1]+ba[acodec^=mp4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]',
    '--merge-output-format', 'mp4',
    '--remux-video', 'mp4',
    '-o', template,
    watchUrl
  ];

  console.log('Public proxy path failed; trying live YouTube guest-browser session.');
  try {
    await run(YTDLP, args);
  } catch (firstError) {
    console.log('Guest-browser tv/web clients failed; retrying with web creator/mweb clients:', String(firstError?.message || firstError));
    await run(YTDLP, [
      ...args.slice(0, args.indexOf('--extractor-args')),
      '--extractor-args', 'youtube:player_client=web_creator,mweb;formats=missing_pot,duplicate',
      ...args.slice(args.indexOf('--extractor-args') + 2)
    ]);
  }

  const base = path.basename(out, '.mp4');
  const dir = path.dirname(out);
  const candidates = fs.readdirSync(dir)
    .filter(x => x === path.basename(out) || x.startsWith(base + '.'))
    .map(x => path.join(dir, x))
    .filter(x => fs.existsSync(x) && fs.statSync(x).size > 250000)
    .sort((a,b) => fs.statSync(b).size - fs.statSync(a).size);

  if (!candidates.length) throw new Error('Browser-session yt-dlp did not create a usable media cut.');
  const src = candidates[0];
  if (src !== out) {
    await run(ffmpegPath, [
      '-y','-hide_banner','-loglevel','error','-i',src,'-t',String(duration),
      '-map','0:v:0','-map','0:a:0?',
      '-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p',
      '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',out
    ]);
    try { fs.unlinkSync(src); } catch {}
  }
  if (!fs.existsSync(out) || fs.statSync(out).size < 250000) {
    throw new Error('Browser-session media cut was unexpectedly small.');
  }
  return { out, source: 'youtube-live-guest-browser', title: '' };
}

async function resolvePublicMuxed(videoId) {
  const errors = [];
  const pipedApis = [
    'https://pipedapi.kavin.rocks',
    'https://pipedapi.leptons.xyz',
    'https://pipedapi.nosebs.ru',
    'https://pipedapi.moomoo.me',
    'https://pipedapi.syncpundit.io',
    'https://api-piped.mha.fi',
    'https://piped-api.garudalinux.org'
  ];
  const qualityNumber = x => {
    const q = String(x?.quality || x?.qualityLabel || '').match(/\d+/);
    return q ? Number(q[0]) : 0;
  };
  const streamUrl = (x, base) => {
    const u = String(x?.url || '').trim();
    if (!u) return '';
    try { return new URL(u, base).href; } catch { return ''; }
  };

  for (const api of pipedApis) {
    try {
      const d = await fetchJson(`${api}/streams/${encodeURIComponent(videoId)}`, {}, 30000);
      const videoRows = Array.isArray(d.videoStreams) ? d.videoStreams : [];
      const audioRows = Array.isArray(d.audioStreams) ? d.audioStreams : [];

      const muxed = videoRows
        .map(x => ({...x, resolvedUrl: streamUrl(x, api), q: qualityNumber(x)}))
        .filter(x => x.resolvedUrl && x.videoOnly === false)
        .sort((a,b) => {
          const aq = a.q && a.q <= 720 ? a.q : 0;
          const bq = b.q && b.q <= 720 ? b.q : 0;
          return bq - aq;
        });
      const muxedPreferred = muxed.find(x => x.q > 0 && x.q <= 720) || muxed[0];
      if (muxedPreferred) {
        console.log('Automatic source resolved through Piped muxed', api, 'quality', muxedPreferred.q || 'unknown');
        return { url: muxedPreferred.resolvedUrl, source: `piped:${api}`, title: String(d.title || '') };
      }

      const videos = videoRows
        .map(x => ({...x, resolvedUrl: streamUrl(x, api), q: qualityNumber(x)}))
        .filter(x => x.resolvedUrl)
        .sort((a,b) => {
          const aq = a.q && a.q <= 720 ? a.q : 0;
          const bq = b.q && b.q <= 720 ? b.q : 0;
          return bq - aq;
        });
      const video = videos.find(x => x.q > 0 && x.q <= 720) || videos[0];
      const audios = audioRows
        .map(x => ({...x, resolvedUrl: streamUrl(x, api), br: Number(x.bitrate || 0)}))
        .filter(x => x.resolvedUrl)
        .sort((a,b) => b.br - a.br);
      const audio = audios[0];

      if (video && audio) {
        console.log('Automatic source resolved through Piped adaptive pair', api, 'quality', video.q || 'unknown');
        return { videoUrl: video.resolvedUrl, audioUrl: audio.resolvedUrl, source: `piped-pair:${api}`, title: String(d.title || '') };
      }
      errors.push(`${api}: no usable media streams`);
    } catch (e) {
      errors.push(`${api}: ${String(e?.message || e).slice(0,180)}`);
    }
  }

  for (const api of AUTO_SOURCE_APIS) {
    try {
      const d = await fetchJson(`${api}/api/v1/videos/${encodeURIComponent(videoId)}`);
      const rows = (d.formatStreams || [])
        .map(x => ({
          url: String(x.url || ''),
          q: Number(String(x.qualityLabel || x.quality || '').replace(/\D/g,'') || 0),
          mime: String(x.type || x.mimeType || '')
        }))
        .filter(x => x.url.startsWith('http') && /video\/mp4/i.test(x.mime))
        .sort((a,b) => (Math.min(b.q || 0,720) - Math.min(a.q || 0,720)));
      const preferred = rows.find(x => x.q <= 720) || rows[0];
      if (preferred) {
        console.log('Automatic public source resolved through', api, 'quality', preferred.q);
        return { url: preferred.url, source: `invidious:${api}`, title: String(d.title || '') };
      }
      errors.push(`${api}: no muxed MP4`);
    } catch (e) {
      errors.push(`${api}: ${String(e?.message || e).slice(0,180)}`);
    }
  }

  const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
  for (const api of AUTO_COBALT_APIS) {
    try {
      const d = await fetchJson(api, {
        method: 'POST',
        headers: {'content-type':'application/json'},
        body: JSON.stringify({
          url: watchUrl,
          videoQuality: '720',
          youtubeVideoCodec: 'h264',
          downloadMode: 'auto',
          filenameStyle: 'basic',
          alwaysProxy: true
        })
      }, 45000);
      const u = String(d.url || '');
      if (u.startsWith('http') && ['tunnel','redirect'].includes(String(d.status || ''))) {
        console.log('Automatic public source resolved through Cobalt', api);
        return { url: u, source: `cobalt:${api}`, title: '' };
      }
      errors.push(`${api}: ${String(d.status || 'no-url')}`);
    } catch (e) {
      errors.push(`${api}: ${String(e?.message || e).slice(0,180)}`);
    }
  }
  throw new Error('Automatic public source resolution failed: ' + errors.join(' | '));
}

async function buildAutomaticCut(videoId, start, duration) {
  // Prefer lightweight public transports first. The prior browser-first flow
  // launched a second Chromium context alongside the TV browser and could
  // restart the small Render instance before the fallbacks were ever tried.
  let resolved;
  try {
    resolved = await resolvePublicMuxed(videoId);
  } catch (publicError) {
    console.warn('Public media fallbacks failed; trying live YouTube guest-browser session:', String(publicError?.message || publicError).slice(0, 1400));
    return await buildBrowserSessionCut(videoId, start, duration);
  }
  const out = path.join('/tmp', `rubyclips-auto-${videoId}-${Math.round(start)}-${Date.now()}.mp4`);
  const commonOut = [
    '-t', String(duration),
    '-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart', out
  ];

  if (resolved.videoUrl && resolved.audioUrl) {
    await run(ffmpegPath, [
      '-y','-hide_banner','-loglevel','warning',
      '-rw_timeout','30000000',
      '-reconnect','1','-reconnect_streamed','1','-reconnect_delay_max','5',
      '-ss', String(start), '-i', resolved.videoUrl,
      '-ss', String(start), '-i', resolved.audioUrl,
      '-map','0:v:0','-map','1:a:0?',
      ...commonOut
    ]);
  } else {
    await run(ffmpegPath, [
      '-y','-hide_banner','-loglevel','warning',
      '-rw_timeout','30000000',
      '-reconnect','1','-reconnect_streamed','1','-reconnect_delay_max','5',
      '-ss', String(start), '-i', resolved.url,
      '-map','0:v:0','-map','0:a:0?',
      ...commonOut
    ]);
  }

  if (!fs.existsSync(out) || fs.statSync(out).size < 250000) {
    try { fs.unlinkSync(out); } catch {}
    throw new Error('Automatic cut was not created or was unexpectedly small');
  }
  return { out, source: resolved.source, title: resolved.title };
}

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
app.get('/api/auto-cut', async (req,res) => {
  const videoId = String(req.query.v || '').trim();
  const start = Math.max(0, Number(req.query.start || 0));
  const duration = Math.min(590, Math.max(5, Number(req.query.duration || 580)));
  if (!/^[A-Za-z0-9_-]{6,20}$/.test(videoId)) return res.status(400).json({ok:false,error:'invalid video id'});
  let built = null;
  try {
    console.log('Automatic Rubaradaclips cut request', {videoId,start,duration});
    built = await buildAutomaticCut(videoId, start, duration);
    res.setHeader('x-rubyclips-source', built.source);
    res.setHeader('cache-control','no-store');
    res.sendFile(built.out, err => {
      try { fs.unlinkSync(built.out); } catch {}
      if (err) console.error('auto-cut send error', err);
    });
  } catch (e) {
    if (built?.out) try { fs.unlinkSync(built.out); } catch {}
    console.error('Automatic Rubaradaclips cut failed:', e);
    res.status(502).json({ok:false,error:String(e?.message || e)});
  }
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
  // Keep the small Render instance idle until /api/auto-cut actually needs
  // a browser. Running the TV QR browser permanently plus the on-demand guest
  // browser could exhaust memory and restart the service mid-download.
  setStatus({stage:'standby',signedIn:false,downloading:false,error:null});
  console.log('Rubradaclips source bridge standing by; guest browser launches on demand.');
}

boot();
