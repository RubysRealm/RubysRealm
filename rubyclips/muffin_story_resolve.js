const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const puppeteer = require('puppeteer-core');
const Tiktok = require('@tobyg74/tiktok-api-dl');

const BASE = 'rubyclips';
const WORK = path.join(BASE, 'muffin_work');
const STATE_PATH = path.join(BASE, 'muffin_state.json');
const LOOKAHEAD_EPISODES = 12;
const PACKING_TARGET_SECONDS = 590.0;
const AUTHOR = 'muffindrama_us';
const KNOWN_EPISODE_IDS = {
  1: '7682997000391904526',
  2: '7682997015172762893',
  3: '7682996961800244494',
  4: '7682996995631385869',
  5: '7682997029995318541',
  6: '7682996992389156109',
  7: '7682996978749377806',
  8: '7682997017148132621',
  9: '7682997019178192142',
  10: '7682997003072064781',
  11: '7682997042762812685',
  12: '7682996981949582605',
  13: '7682997023217306893',
  14: '7682996977897917709',
  15: '7682996991823056141',
  39: '7680667081213234450'
};

const state = JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'));
const seriesId = String(state.currentSeriesId);
const firstEpisode = Number(state.nextEpisode);
const episodeCount = Number(state.currentSeriesEpisodeCount);
if (!Number.isInteger(firstEpisode) || firstEpisode < 1 || firstEpisode > episodeCount) throw new Error(`No unresolved episode available: next=${firstEpisode}, total=${episodeCount}`);

fs.mkdirSync(WORK, { recursive: true });
for (const name of fs.readdirSync(WORK)) {
  if (/^ep\d+\.mp4$/.test(name) || ['episodes.json','selected.json','concat.txt'].includes(name)) { try { fs.unlinkSync(path.join(WORK, name)); } catch {} }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const chrome = ['/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'].find(p => fs.existsSync(p));

async function resolveMedia(videoId, episode, sourceHint = 'candidate') {
  const sourceUrl = `https://www.tiktok.com/@${AUTHOR}/video/${videoId}`;
  for (let attempt = 1; attempt <= 4; attempt++) {
    try {
      const result = await Tiktok.Downloader(sourceUrl, { version: 'v2' });
      const media = result?.result?.video?.playAddr?.[0];
      const nickname = String(result?.result?.author?.nickname || '').toLowerCase();
      if (result?.status === 'success' && media && (!nickname || nickname.includes('muffin'))) return { episode, sourceUrl, shortDramaUrl: `https://www.tiktok.com/shortdrama/episode/${seriesId}/${episode}`, videoId: String(videoId), media, sourceHint };
    } catch (e) { if (attempt === 4) console.error(`Episode ${episode}, ${videoId}: ${e.message}`); }
    await sleep(1000 * attempt);
  }
  return null;
}

function collectVideoIds(text) {
  if (!text) return [];
  const out = [], s = String(text);
  const patterns = [new RegExp(`@${AUTHOR}\\/video\\/(\\d{10,25})`, 'gi'), /["'](?:aweme_id|awemeId|itemId|item_id|videoId|video_id|group_id|groupId)["']\s*[:=]\s*["']?(\d{10,25})/gi, /aweme\/detail\/(\d{10,25})/gi, /[?&]item_id=(\d{10,25})/gi];
  for (const re of patterns) for (const m of s.matchAll(re)) out.push(m[1]);
  return [...new Set(out)];
}

function itemIdFromUrl(value) {
  const m = String(value || '').match(/[?&]item_id=(\d{10,25})/i);
  return m ? m[1] : null;
}

async function browserFallback(episode) {
  if (!chrome) return null;
  const browser = await puppeteer.launch({ headless: true, executablePath: chrome, args: ['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required'] });
  try {
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36');
    await page.setViewport({ width: 1440, height: 1800 });
    const captured = [];
    const directMedia = new Map();
    const targetId = String(KNOWN_EPISODE_IDS[episode] || '');
    const capture = value => {
      if (!value) return;
      const s = String(value);
      for (const id of collectVideoIds(s)) if (id !== seriesId && !captured.includes(id)) captured.push(id);
      const id = itemIdFromUrl(s);
      if (id && /\/aweme\/v1\/play\//i.test(s) && !directMedia.has(id)) directMedia.set(id, s);
    };
    page.on('request', req => capture(req.url()));
    page.on('response', resp => {
      const u = resp.url();
      capture(u);
      const id = itemIdFromUrl(u);
      if (id && /\/aweme\/v1\/play\//i.test(u)) {
        const location = resp.headers()?.location;
        if (location) directMedia.set(id, location);
      }
    });

    const targetUrl = `https://www.tiktok.com/shortdrama/episode/${seriesId}/${episode}`;
    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await sleep(4500);

    async function clickEpisodeNumber() {
      return page.evaluate((n) => {
        const wanted = String(n);
        const els = [...document.querySelectorAll('button,[role="button"],a')];
        const el = els.find(x => (x.textContent || '').trim() === wanted || (x.getAttribute('aria-label') || '').trim() === wanted);
        if (!el) return false;
        el.click();
        return true;
      }, episode).catch(() => false);
    }

    if (!(targetId && directMedia.has(targetId))) {
      await clickEpisodeNumber();
      await sleep(5000);
    }

    if (!(targetId && directMedia.has(targetId)) && episode > 1) {
      const priorUrl = `https://www.tiktok.com/shortdrama/episode/${seriesId}/${episode - 1}`;
      await page.goto(priorUrl, { waitUntil: 'domcontentloaded', timeout: 90000 });
      await sleep(3500);
      await clickEpisodeNumber();
      await sleep(7000);
    }

    const d = await page.evaluate(() => ({ location: location.href, canonical: document.querySelector('link[rel="canonical"]')?.href || '', appLinks: [...document.querySelectorAll('meta[property="al:ios:url"],meta[property="al:android:url"]')].map(x => x.content || ''), html: document.documentElement?.outerHTML || '', scripts: [...document.scripts].map(s => s.textContent || '').join('\n'), resources: performance.getEntriesByType('resource').map(x => x.name) }));
    capture(d.location); capture(d.canonical); capture(d.html); capture(d.scripts); for (const x of d.appLinks) capture(x); for (const x of d.resources) capture(x);

    const cookies = await page.cookies().catch(() => []);
    const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ');
    if (targetId && directMedia.has(targetId)) {
      const media = directMedia.get(targetId);
      console.log(`Episode ${episode}: captured rendered TikTok media stream for item ${targetId}.`);
      return { episode, sourceUrl: `https://www.tiktok.com/@${AUTHOR}/video/${targetId}`, shortDramaUrl: targetUrl, videoId: targetId, media, cookieHeader, sourceHint: 'shortdrama-rendered-play-stream' };
    }

    for (const [id, media] of directMedia.entries()) {
      if (captured.includes(id)) {
        console.log(`Episode ${episode}: using captured rendered media stream ${id}.`);
        return { episode, sourceUrl: `https://www.tiktok.com/@${AUTHOR}/video/${id}`, shortDramaUrl: targetUrl, videoId: id, media, cookieHeader, sourceHint: 'shortdrama-rendered-play-stream' };
      }
    }

    for (const id of captured.slice(0, 40)) { const resolved = await resolveMedia(id, episode, 'shortdrama-browser'); if (resolved) return resolved; }
    return null;
  } catch (e) { console.error(`Episode ${episode} browser fallback: ${e.message}`); return null; }
  finally { await browser.close(); }
}

async function identifyEpisodeVideo(episode) {
  const known = KNOWN_EPISODE_IDS[episode];
  if (known) { const resolved = await resolveMedia(known, episode, 'shortdrama-canonical'); if (resolved) return resolved; }
  const fallback = await browserFallback(episode); if (fallback) return fallback;
  throw new Error(`Episode ${episode}: unable to resolve TikTok video ID/media.`);
}

function durationOf(file) {
  return Number(execFileSync('ffprobe', ['-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1', file], { encoding: 'utf8' }).trim());
}

(async () => {
  const resolved = [];
  let packedSeconds = 0;
  const last = Math.min(episodeCount, firstEpisode + LOOKAHEAD_EPISODES - 1);
  for (let episode = firstEpisode; episode <= last; episode++) {
    let item;
    try { item = await identifyEpisodeVideo(episode); }
    catch (e) { if (episode === firstEpisode) throw e; console.error(`Stopping lookahead at Episode ${episode}: ${e.message}`); break; }

    const file = path.join(WORK, `ep${episode}.mp4`);
    let dur;
    try {
      const curlArgs = ['-L','--fail','--retry','3','--retry-delay','1','--connect-timeout','25','-A','Mozilla/5.0','-e', item.shortDramaUrl || 'https://www.tiktok.com/'];
      if (item.cookieHeader) curlArgs.push('-H', `Cookie: ${item.cookieHeader}`);
      curlArgs.push(item.media, '-o', file);
      execFileSync('curl', curlArgs, { stdio: 'inherit' });
      const size = fs.existsSync(file) ? fs.statSync(file).size : 0;
      if (size < 100000) throw new Error(`downloaded file is too small (${size} bytes)`);
      dur = durationOf(file);
      if (!Number.isFinite(dur) || dur <= 0) throw new Error(`invalid duration ${dur}`);
    } catch (e) {
      try { if (fs.existsSync(file)) fs.unlinkSync(file); } catch {}
      if (episode === firstEpisode || resolved.length === 0) throw new Error(`Episode ${episode}: download/verify failed: ${e.message}`);
      console.error(`Stopping lookahead at Episode ${episode}: download/verify failed: ${e.message}`);
      break;
    }

    if (resolved.length && packedSeconds + dur > PACKING_TARGET_SECONDS) {
      fs.unlinkSync(file);
      console.log(`Episode ${episode} would exceed ${PACKING_TARGET_SECONDS}s; Part ${state.nextPart} is full.`);
      break;
    }

    resolved.push({ episode, sourceUrl: item.sourceUrl, shortDramaUrl: item.shortDramaUrl, videoId: item.videoId, sourceHint: item.sourceHint, file, duration: dur });
    packedSeconds += dur;
    console.log(`Resolved Episode ${episode} -> ${item.videoId} (${item.sourceHint}) ${dur.toFixed(2)}s; packed=${packedSeconds.toFixed(2)}s`);
    if (packedSeconds >= PACKING_TARGET_SECONDS) break;
  }

  if (!resolved.length || Number(resolved[0].episode) !== firstEpisode) throw new Error(`Resolver did not produce required Episode ${firstEpisode}.`);
  fs.writeFileSync(path.join(WORK, 'episodes.json'), JSON.stringify(resolved, null, 2) + '\n');
  console.log(`Prepared ${resolved.length} consecutive episodes starting at ${firstEpisode}; ${packedSeconds.toFixed(2)} seconds.`);
})().catch(err => { console.error(err); process.exit(1); });
