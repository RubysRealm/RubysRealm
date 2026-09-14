const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const puppeteer = require('puppeteer-core');
const Tiktok = require('@tobyg74/tiktok-api-dl');

const BASE = 'rubyclips';
const WORK = path.join(BASE, 'muffin_work');
const STATE_PATH = path.join(BASE, 'muffin_state.json');
const LOOKAHEAD_EPISODES = 12;
const AUTHOR = 'muffindrama_us';
const KNOWN_EPISODE_IDS = {
  1: '7682997000391904526',
  4: '7682996995631385869',
  5: '7682997029995318541',
  6: '7682996992389156109',
  7: '7682996978749377806',
  8: '7682997017148132621',
  9: '7682997019178192142',
  10: '7682997003072064781',
  13: '7682997023217306893',
  15: '7682996991823056141'
};

const state = JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'));
const seriesId = String(state.currentSeriesId);
const firstEpisode = Number(state.nextEpisode);
const episodeCount = Number(state.currentSeriesEpisodeCount);
if (!Number.isInteger(firstEpisode) || firstEpisode < 1 || firstEpisode > episodeCount) {
  throw new Error(`No unresolved episode available: next=${firstEpisode}, total=${episodeCount}`);
}

fs.mkdirSync(WORK, { recursive: true });
for (const name of fs.readdirSync(WORK)) {
  if (/^ep\d+\.mp4$/.test(name) || ['episodes.json','selected.json','concat.txt'].includes(name)) {
    try { fs.unlinkSync(path.join(WORK, name)); } catch {}
  }
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
      if (result?.status === 'success' && media && (!nickname || nickname.includes('muffin'))) {
        return { episode, sourceUrl, shortDramaUrl: `https://www.tiktok.com/shortdrama/episode/${seriesId}/${episode}`, videoId: String(videoId), media, sourceHint };
      }
    } catch (e) {
      if (attempt === 4) console.error(`Episode ${episode}, ${videoId}: ${e.message}`);
    }
    await sleep(1000 * attempt);
  }
  return null;
}

function collectVideoIds(text) {
  if (!text) return [];
  const out = [];
  const s = String(text);
  const patterns = [
    new RegExp(`@${AUTHOR}\\/video\\/(\\d{10,25})`, 'gi'),
    /["'](?:aweme_id|awemeId|itemId|item_id|videoId|video_id|group_id|groupId)["']\s*[:=]\s*["']?(\d{10,25})/gi,
    /aweme\/detail\/(\d{10,25})/gi
  ];
  for (const re of patterns) for (const m of s.matchAll(re)) out.push(m[1]);
  return [...new Set(out)];
}

async function browserFallback(episode) {
  if (!chrome) return null;
  const browser = await puppeteer.launch({ headless: true, executablePath: chrome, args: ['--no-sandbox','--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36');
    await page.setViewport({ width: 1440, height: 1800 });
    const captured = [];
    const capture = value => {
      for (const id of collectVideoIds(value)) if (id !== seriesId && !captured.includes(id)) captured.push(id);
    };
    page.on('request', req => capture(req.url()));
    page.on('response', resp => capture(resp.url()));
    const target = `https://www.tiktok.com/shortdrama/episode/${seriesId}/${episode}`;
    await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 90000 });
    await sleep(8000);
    const pageData = await page.evaluate(() => ({
      location: location.href,
      canonical: document.querySelector('link[rel="canonical"]')?.href || '',
      appLinks: [...document.querySelectorAll('meta[property="al:ios:url"],meta[property="al:android:url"]')].map(x => x.content || ''),
      html: document.documentElement?.outerHTML || '',
      scripts: [...document.scripts].map(s => s.textContent || '').join('\n'),
      resources: performance.getEntriesByType('resource').map(x => x.name)
    }));
    capture(pageData.location); capture(pageData.canonical); capture(pageData.html); capture(pageData.scripts);
    for (const x of pageData.appLinks) capture(x);
    for (const x of pageData.resources) capture(x);
    await page.close();
    for (const id of captured.slice(0, 40)) {
      const resolved = await resolveMedia(id, episode, 'shortdrama-browser');
      if (resolved) return resolved;
    }
    return null;
  } catch (e) {
    console.error(`Episode ${episode} browser fallback: ${e.message}`);
    return null;
  } finally {
    await browser.close();
  }
}

async function identifyEpisodeVideo(episode) {
  const known = KNOWN_EPISODE_IDS[episode];
  if (known) {
    const resolved = await resolveMedia(known, episode, 'shortdrama-canonical');
    if (resolved) return resolved;
  }
  const fallback = await browserFallback(episode);
  if (fallback) return fallback;
  throw new Error(`Episode ${episode}: unable to resolve TikTok video ID/media.`);
}

(async () => {
  const resolved = [];
  const last = Math.min(episodeCount, firstEpisode + LOOKAHEAD_EPISODES - 1);
  for (let episode = firstEpisode; episode <= last; episode++) {
    let item;
    try { item = await identifyEpisodeVideo(episode); }
    catch (e) {
      if (episode === firstEpisode) throw e;
      console.error(`Stopping lookahead at Episode ${episode}: ${e.message}`);
      break;
    }
    const file = path.join(WORK, `ep${episode}.mp4`);
    execFileSync('curl', ['-L','--fail','--retry','3','--retry-delay','1','--connect-timeout','25','-A','Mozilla/5.0','-e','https://www.tiktok.com/', item.media, '-o', file], { stdio: 'inherit' });
    if (fs.statSync(file).size < 100000) throw new Error(`Episode ${episode}: downloaded file is too small.`);
    resolved.push({ episode, sourceUrl: item.sourceUrl, shortDramaUrl: item.shortDramaUrl, videoId: item.videoId, sourceHint: item.sourceHint, file });
    console.log(`Resolved Episode ${episode} -> ${item.videoId} (${item.sourceHint})`);
  }
  if (!resolved.length || Number(resolved[0].episode) !== firstEpisode) throw new Error(`Resolver did not produce required Episode ${firstEpisode}.`);
  fs.writeFileSync(path.join(WORK, 'episodes.json'), JSON.stringify(resolved, null, 2) + '\n');
  console.log(`Prepared ${resolved.length} consecutive episodes starting at ${firstEpisode}.`);
})().catch(err => { console.error(err); process.exit(1); });
