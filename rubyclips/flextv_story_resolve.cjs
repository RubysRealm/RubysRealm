const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const puppeteer = require('puppeteer-core');

const BASE = 'rubyclips';
const WORK = path.join(BASE, 'muffin_work');
const STATE_PATH = path.join(BASE, 'muffin_state.json');
const MAX_SECONDS = 590;
const HARD_MAX_SECONDS = 598.5;
const CATALOG_URL = 'https://www.flextv.cc/dramas/all-dramas';
const FLEX_CHANNEL = 'flextv.cc';
const sleep = ms => new Promise(r => setTimeout(r, ms));

function run(cmd, args, opts = {}) {
  console.log('+', cmd, args.join(' '));
  return execFileSync(cmd, args, { stdio: 'inherit', ...opts });
}
function output(cmd, args) {
  return execFileSync(cmd, args, { encoding: 'utf8' }).trim();
}
function duration(file) {
  return Number(output('ffprobe', ['-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',file]));
}
function streamTypes(file) {
  return output('ffprobe', ['-v','error','-show_entries','stream=codec_type','-of','csv=p=0',file]).split(/\s+/).filter(Boolean);
}
function findChrome() {
  for (const p of ['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium','/usr/bin/chromium-browser']) {
    if (fs.existsSync(p)) return p;
  }
  for (const name of ['google-chrome','google-chrome-stable','chromium','chromium-browser']) {
    try { const p = output('which', [name]); if (p) return p; } catch {}
  }
  throw new Error('No Chrome/Chromium executable found on runner.');
}
function cleanUrl(s) {
  return String(s || '').replace(/\\u002F/gi, '/').replace(/\\\//g, '/').replace(/&amp;/g, '&').replace(/["'<>),;]+$/g, '');
}
function extractHttpUrls(text) {
  const t = String(text || '').replace(/\\u002F/gi, '/').replace(/\\\//g, '/');
  return [...t.matchAll(/https?:\/\/[^\s"'<>\\]+/g)].map(m => cleanUrl(m[0]));
}
function isMediaUrl(u) {
  const s = String(u || '').toLowerCase();
  return /^https?:\/\//.test(s) && (s.includes('.m3u8') || s.includes('.mp4') || s.includes('.mpd'));
}
function mediaScore(u) {
  const s = u.toLowerCase();
  let n = 0;
  if (s.includes('.m3u8')) n += 100;
  if (s.includes('master')) n += 20;
  if (s.includes('playlist')) n += 10;
  if (s.includes('file-cdn.flextv.cc') || s.includes('resources-sgp-auth.flextv.cc')) n += 8;
  if (s.includes('.mp4')) n += 5;
  return n;
}
function parseSeriesFromEpisodeUrl(url) {
  const m = String(url).match(/\/episodes\/episode-1-(.+)-([A-Za-z0-9]{10})(?:[?#].*)?$/);
  if (!m) return null;
  return { slug: m[1], id: m[2], episode1Url: url.split(/[?#]/)[0] };
}
function episodeUrl(series, ep) {
  return `https://www.flextv.cc/episodes/episode-${ep}-${series.slug}-${series.id}`;
}
function writeState(s) {
  fs.writeFileSync(STATE_PATH, JSON.stringify(s, null, 2) + '\n');
}
function commitState(message) {
  try {
    run('git', ['config','user.name','rubyclips-publisher-bot']);
    run('git', ['config','user.email','actions@users.noreply.github.com']);
    run('git', ['add', STATE_PATH]);
    try { run('git', ['diff','--cached','--quiet']); return; } catch {}
    run('git', ['commit','-m',message]);
    run('git', ['push']);
  } catch (e) {
    throw new Error(`Failed to persist FlexTV story state: ${e.message}`);
  }
}

async function clickPlay(page) {
  try {
    await page.evaluate(() => {
      const video = document.querySelector('video');
      if (video) {
        video.muted = true;
        video.playsInline = true;
        video.play().catch(() => {});
        video.click();
      }
      const nodes = [...document.querySelectorAll('button,[role="button"],div')];
      const el = nodes.find(x => {
        const t = `${x.getAttribute?.('aria-label') || ''} ${x.getAttribute?.('title') || ''} ${x.textContent || ''}`.trim().toLowerCase();
        return t === 'play' || t.includes('play video') || t.includes('watch free');
      });
      if (el) el.click();
    });
  } catch {}
}

async function inspectEpisode(browser, series, ep, extraWait = 2500) {
  const url = episodeUrl(series, ep);
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  await page.setExtraHTTPHeaders({ 'accept-language': 'en-US,en;q=0.9' });
  const candidates = new Set();
  const apiUrls = new Set();
  const responseTasks = [];

  page.on('request', req => {
    const u = cleanUrl(req.url());
    if (isMediaUrl(u)) candidates.add(u);
    if (/api(?:-quick)?\.flextv\.cc|\/api\//i.test(u)) apiUrls.add(u);
  });
  page.on('response', res => {
    const u = cleanUrl(res.url());
    if (isMediaUrl(u)) candidates.add(u);
    if (!/api(?:-quick)?\.flextv\.cc|file-cdn\.flextv\.cc|resources-sgp-auth\.flextv\.cc/i.test(u)) return;
    apiUrls.add(u);
    const task = (async () => {
      try {
        const headers = res.headers();
        const ct = String(headers['content-type'] || '').toLowerCase();
        if (!(ct.includes('json') || ct.includes('text') || ct.includes('javascript') || ct.includes('mpegurl'))) return;
        const txt = await res.text();
        for (const x of extractHttpUrls(txt)) if (isMediaUrl(x)) candidates.add(x);
      } catch {}
    })();
    responseTasks.push(task);
  });

  console.log(`Inspecting FlexTV Episode ${ep}: ${url}`);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(1800);
  await clickPlay(page);
  await sleep(extraWait);
  await clickPlay(page);
  await sleep(1200);

  try {
    const runtime = await page.evaluate(() => ({
      title: document.querySelector('h1')?.textContent?.trim() || document.title || '',
      currentSrc: document.querySelector('video')?.currentSrc || document.querySelector('video')?.src || '',
      duration: Number(document.querySelector('video')?.duration || 0),
      resources: performance.getEntriesByType('resource').map(x => x.name).filter(Boolean),
      hrefs: [...document.querySelectorAll('a[href]')].map(a => a.href).filter(Boolean),
    }));
    if (isMediaUrl(runtime.currentSrc)) candidates.add(cleanUrl(runtime.currentSrc));
    for (const x of runtime.resources || []) if (isMediaUrl(x)) candidates.add(cleanUrl(x));
    await Promise.allSettled(responseTasks);
    const cookies = await page.cookies();
    const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ');
    const ua = await page.evaluate(() => navigator.userAgent);
    const media = [...candidates].filter(isMediaUrl).sort((a,b) => mediaScore(b) - mediaScore(a));
    const d = Number.isFinite(runtime.duration) && runtime.duration > 0 ? runtime.duration : 0;
    await page.close();
    return { episode: ep, sourceUrl: url, title: runtime.title, duration: d, media, apiUrls: [...apiUrls], cookieHeader, ua };
  } catch (e) {
    await page.close().catch(() => {});
    throw e;
  }
}

function remoteProbe(meta) {
  for (const media of meta.media) {
    const hdr = `Referer: ${meta.sourceUrl}\r\nOrigin: https://www.flextv.cc\r\nUser-Agent: ${meta.ua}\r\n${meta.cookieHeader ? `Cookie: ${meta.cookieHeader}\r\n` : ''}`;
    try {
      const v = Number(output('ffprobe', ['-v','error','-headers',hdr,'-show_entries','format=duration','-of','default=nw=1:nk=1',media]));
      if (Number.isFinite(v) && v > 1) return v;
    } catch {}
  }
  return 0;
}

function downloadEpisode(meta, out) {
  if (!meta.media.length) throw new Error(`Episode ${meta.episode}: no runtime media URL captured. API requests: ${meta.apiUrls.slice(0,8).join(', ')}`);
  const hdr = `Referer: ${meta.sourceUrl}\r\nOrigin: https://www.flextv.cc\r\nUser-Agent: ${meta.ua}\r\n${meta.cookieHeader ? `Cookie: ${meta.cookieHeader}\r\n` : ''}`;
  let lastErr;
  for (const media of meta.media) {
    try {
      if (fs.existsSync(out)) fs.unlinkSync(out);
      run('ffmpeg', ['-y','-hide_banner','-loglevel','error','-headers',hdr,'-i',media,'-map','0:v:0','-map','0:a:0?','-c','copy','-movflags','+faststart',out], { timeout: 900000 });
      if (!fs.existsSync(out) || fs.statSync(out).size < 300000) throw new Error('downloaded file is too small');
      const d = duration(out);
      const types = streamTypes(out);
      if (!(d > 3 && d <= HARD_MAX_SECONDS) || !types.includes('video') || !types.includes('audio')) throw new Error(`invalid media duration/streams: ${d}s ${types.join(',')}`);
      return d;
    } catch (e) {
      lastErr = e;
      console.error(`Episode ${meta.episode} media candidate failed: ${media} :: ${e.message}`);
    }
  }
  throw new Error(`Episode ${meta.episode}: all captured FlexTV media URLs failed: ${lastErr?.message || 'unknown error'}`);
}

function packCount(durations) {
  let parts = 0, sum = 0, has = false;
  for (const d0 of durations) {
    const d = Number(d0);
    if (!(d > 0 && d <= HARD_MAX_SECONDS)) throw new Error(`Invalid episode duration while counting parts: ${d0}`);
    if (has && sum + d > MAX_SECONDS) { parts++; sum = 0; has = false; }
    sum += d; has = true;
    if (sum >= MAX_SECONDS) { parts++; sum = 0; has = false; }
  }
  if (has) parts++;
  return parts;
}

async function discoverNextSeries(browser, completedIds) {
  const page = await browser.newPage();
  await page.goto(CATALOG_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(2500);
  const hrefs = await page.evaluate(() => [...document.querySelectorAll('a[href]')].map(a => a.href).filter(Boolean));
  await page.close();
  const unique = [];
  const seen = new Set();
  for (const href of hrefs) {
    const parsed = parseSeriesFromEpisodeUrl(href);
    if (!parsed || seen.has(parsed.id) || completedIds.has(parsed.id)) continue;
    seen.add(parsed.id); unique.push(parsed);
  }
  if (!unique.length) throw new Error('FlexTV catalog did not expose an uncompleted Episode 1 link.');
  const selected = unique[0];
  const probe = await browser.newPage();
  await probe.goto(selected.episode1Url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await sleep(1800);
  const info = await probe.evaluate(() => {
    const h1 = document.querySelector('h1')?.textContent?.trim() || '';
    const title = h1.replace(/^Watch\s+/i,'').replace(/\s+Episode\s+1.*$/i,'').trim();
    const eps = [...document.querySelectorAll('a[href*="/episodes/episode-"]')].map(a => {
      const m = a.href.match(/\/episodes\/episode-(\d+)-/); return m ? Number(m[1]) : 0;
    }).filter(Boolean);
    return { title, episodeCount: eps.length ? Math.max(...eps) : 0 };
  });
  await probe.close();
  if (!info.title || !info.episodeCount) throw new Error(`Could not read FlexTV series metadata for ${selected.episode1Url}`);
  return { ...selected, title: info.title, episodeCount: info.episodeCount };
}

(async () => {
  fs.mkdirSync(WORK, { recursive: true });
  for (const name of fs.readdirSync(WORK)) {
    if (/^ep\d+\.mp4$/.test(name) || ['episodes.json','selected.json','concat.txt','continuation.json'].includes(name)) {
      try { fs.unlinkSync(path.join(WORK, name)); } catch {}
    }
  }

  let state = JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'));
  const browser = await puppeteer.launch({
    executablePath: findChrome(), headless: true,
    args: ['--no-sandbox','--disable-setuid-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required']
  });

  try {
    if (state.currentSeriesComplete === true) {
      const completed = new Set((state.completedSeriesIds || []).map(String));
      const next = await discoverNextSeries(browser, completed);
      state.sourceProvider = 'flextv';
      state.sourceChannel = FLEX_CHANNEL;
      state.currentSeriesId = next.id;
      state.flexSeriesSlug = next.slug;
      state.currentSeriesTitle = next.title;
      state.currentSeriesEpisodeCount = next.episodeCount;
      state.restartGeneration = 2;
      state.nextEpisode = 1;
      state.nextPart = 1;
      state.lastPostedPart = 0;
      state.lastPostedEpisodes = [];
      state.currentSeriesComplete = false;
      delete state.storyTotalParts;
      delete state.flexEpisodeDurations;
      writeState(state);
      commitState(`Start next FlexTV Rubaradaclips story: ${next.title} [skip ci]`);
      console.log(`Selected next FlexTV story: ${next.title} (${next.id}), ${next.episodeCount} episodes.`);
    }

    if (String(state.sourceProvider || '').toLowerCase() !== 'flextv') throw new Error('FlexTV resolver called for non-FlexTV state.');
    const series = {
      id: String(state.currentSeriesId),
      slug: String(state.flexSeriesSlug || ''),
      title: String(state.currentSeriesTitle || ''),
      episodeCount: Number(state.currentSeriesEpisodeCount)
    };
    if (!/^[A-Za-z0-9]{10}$/.test(series.id) || !series.slug || !series.title || !(series.episodeCount > 0)) throw new Error('Invalid FlexTV series state.');

    const metaCache = new Map();
    let durationMap = state.flexEpisodeDurations && typeof state.flexEpisodeDurations === 'object' ? { ...state.flexEpisodeDurations } : {};
    let needDurationScan = !Number(state.storyTotalParts) || Object.keys(durationMap).length < series.episodeCount;
    if (needDurationScan) {
      console.log(`Scanning ${series.episodeCount} FlexTV episode durations once so Part X of Y is exact.`);
      for (let ep = 1; ep <= series.episodeCount; ep++) {
        if (Number(durationMap[String(ep)]) > 0) continue;
        const meta = await inspectEpisode(browser, series, ep, 1800);
        metaCache.set(ep, meta);
        let d = meta.duration;
        if (!(d > 0)) d = remoteProbe(meta);
        if (!(d > 0 && d <= HARD_MAX_SECONDS)) throw new Error(`Episode ${ep}: could not determine an exact playable duration.`);
        durationMap[String(ep)] = Number(d.toFixed(3));
        console.log(`Episode ${ep} duration ${d.toFixed(2)}s`);
      }
      const orderedDurations = Array.from({ length: series.episodeCount }, (_, i) => Number(durationMap[String(i + 1)]));
      state.flexEpisodeDurations = durationMap;
      state.storyTotalParts = packCount(orderedDurations);
      writeState(state);
      commitState(`Cache FlexTV Rubaradaclips story durations [skip ci]`);
      console.log(`Exact story total: ${state.storyTotalParts} parts.`);
    }

    const first = Number(state.nextEpisode);
    if (!Number.isInteger(first) || first < 1 || first > series.episodeCount) throw new Error(`Bad FlexTV nextEpisode ${first}`);
    const selectedEpisodes = [];
    let seconds = 0;
    for (let ep = first; ep <= series.episodeCount; ep++) {
      const d = Number(durationMap[String(ep)]);
      if (!(d > 0)) throw new Error(`Missing cached duration for Episode ${ep}`);
      if (selectedEpisodes.length && seconds + d > MAX_SECONDS) break;
      selectedEpisodes.push(ep); seconds += d;
      if (seconds >= MAX_SECONDS) break;
    }
    if (!selectedEpisodes.length) throw new Error('No FlexTV episodes selected for this part.');

    const resolved = [];
    for (const ep of selectedEpisodes) {
      const meta = metaCache.get(ep) || await inspectEpisode(browser, series, ep, 2600);
      const out = path.join(WORK, `ep${ep}.mp4`);
      const actual = downloadEpisode(meta, out);
      resolved.push({
        episode: ep,
        sourceUrl: meta.sourceUrl,
        shortDramaUrl: meta.sourceUrl,
        videoId: `${series.id}-e${ep}`,
        sourceHint: 'flextv-runtime-hls',
        sourceProvider: 'flextv',
        sourceChannel: FLEX_CHANNEL,
        file: out,
        duration: actual
      });
      console.log(`FlexTV Episode ${ep} ready: ${actual.toFixed(2)}s`);
    }

    fs.writeFileSync(path.join(WORK, 'episodes.json'), JSON.stringify(resolved, null, 2) + '\n');
    const last = selectedEpisodes[selectedEpisodes.length - 1];
    const storyComplete = last >= series.episodeCount;
    fs.writeFileSync(path.join(WORK, 'continuation.json'), JSON.stringify({
      sourceProvider: 'flextv',
      sourceSeriesId: series.id,
      storyTotalParts: Number(state.storyTotalParts),
      storyComplete,
      nextEpisode: storyComplete ? 1 : last + 1
    }, null, 2) + '\n');
    console.log(`Prepared FlexTV Episodes ${selectedEpisodes.join(', ')} for Part ${state.nextPart} of ${state.storyTotalParts}.`);
  } finally {
    await browser.close().catch(() => {});
  }
})().catch(err => { console.error(err.stack || err); process.exit(1); });
