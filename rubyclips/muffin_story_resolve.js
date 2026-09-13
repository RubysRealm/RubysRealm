const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const puppeteer = require('puppeteer-core');
const { Tiktok } = require('@tobyg74/tiktok-api-dl');

const BASE = 'rubyclips';
const WORK = path.join(BASE, 'muffin_work');
const STATE_PATH = path.join(BASE, 'muffin_state.json');
const LOOKAHEAD_EPISODES = 12;
const AUTHOR = 'muffindrama_us';
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

const chrome = ['/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'].find(p => fs.existsSync(p));
if (!chrome) throw new Error('Chrome/Chromium is missing on runner.');
const sleep = ms => new Promise(r => setTimeout(r, ms));

function collectVideoIds(text) {
  const out = [];
  if (!text) return out;
  const patterns = [
    new RegExp(`@${AUTHOR}\\/video\\/(\\d{10,25})`, 'gi'),
    /["'](?:aweme_id|awemeId|itemId|item_id|videoId|video_id)["']\s*[:=]\s*["']?(\d{10,25})/gi
  ];
  for (const re of patterns) {
    for (const m of String(text).matchAll(re)) out.push(m[1]);
  }
  return [...new Set(out)];
}

async function identifyEpisodeVideo(browser, episode) {
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36');
  await page.setViewport({ width: 1440, height: 1800 });
  const seen = [];
  const capture = url => {
    for (const id of collectVideoIds(url)) if (!seen.includes(id)) seen.push(id);
  };
  page.on('request', req => capture(req.url()));
  page.on('response', resp => capture(resp.url()));

  const target = `https://www.tiktok.com/shortdrama/episode/${seriesId}/${episode}`;
  await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await sleep(9000);

  const pageData = await page.evaluate(() => {
    const canonical = document.querySelector('link[rel="canonical"]')?.href || '';
    const og = document.querySelector('meta[property="og:url"]')?.content || '';
    const anchors = [...document.querySelectorAll('a[href]')].map(a => a.href).filter(Boolean);
    const scripts = [...document.scripts].map(s => s.textContent || '').join('\n');
    const resources = performance.getEntriesByType('resource').map(x => x.name);
    const html = document.documentElement?.outerHTML || '';
    return { location: location.href, canonical, og, anchors, scripts, resources, html };
  });

  const prioritized = [];
  for (const value of [pageData.location, pageData.canonical, pageData.og, ...pageData.anchors, ...pageData.resources, pageData.scripts, pageData.html]) {
    for (const id of collectVideoIds(value)) if (!prioritized.includes(id)) prioritized.push(id);
  }
  for (const id of seen) if (!prioritized.includes(id)) prioritized.push(id);
  await page.close();

  const candidates = prioritized.filter(id => id !== seriesId);
  if (!candidates.length) throw new Error(`Episode ${episode}: no TikTok video ID found.`);

  for (const videoId of candidates.slice(0, 12)) {
    const sourceUrl = `https://www.tiktok.com/@${AUTHOR}/video/${videoId}`;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        const result = await Tiktok.Downloader(sourceUrl, { version: 'v2' });
        const media = result?.result?.video?.playAddr?.[0];
        if (result?.status === 'success' && media) {
          return { episode, sourceUrl, videoId, media, shortDramaUrl: target };
        }
      } catch (e) {
        if (attempt === 3) console.error(`Episode ${episode}, candidate ${videoId}: ${e.message}`);
      }
      await sleep(1000 * attempt);
    }
  }
  throw new Error(`Episode ${episode}: no downloadable TikTok video resolved.`);
}

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    executablePath: chrome,
    args: ['--no-sandbox','--disable-dev-shm-usage']
  });
  const resolved = [];
  try {
    const last = Math.min(episodeCount, firstEpisode + LOOKAHEAD_EPISODES - 1);
    for (let episode = firstEpisode; episode <= last; episode++) {
      let item;
      try {
        item = await identifyEpisodeVideo(browser, episode);
      } catch (e) {
        if (episode === firstEpisode) throw e;
        console.error(`Stopping lookahead at Episode ${episode}: ${e.message}`);
        break;
      }

      const file = path.join(WORK, `ep${episode}.mp4`);
      execFileSync('curl', [
        '-L','--fail','--retry','3','--retry-delay','1','--connect-timeout','25',
        '-A','Mozilla/5.0','-e','https://www.tiktok.com/', item.media, '-o', file
      ], { stdio: 'inherit' });
      if (fs.statSync(file).size < 100000) throw new Error(`Episode ${episode}: downloaded file is too small.`);
      resolved.push({ episode, sourceUrl: item.sourceUrl, shortDramaUrl: item.shortDramaUrl, videoId: item.videoId, file });
      console.log(`Resolved Episode ${episode} -> ${item.videoId}`);
    }
  } finally {
    await browser.close();
  }

  if (!resolved.length || Number(resolved[0].episode) !== firstEpisode) {
    throw new Error(`Resolver did not produce required Episode ${firstEpisode}.`);
  }
  fs.writeFileSync(path.join(WORK, 'episodes.json'), JSON.stringify(resolved, null, 2) + '\n');
  console.log(`Prepared ${resolved.length} consecutive episodes starting at ${firstEpisode}.`);
})().catch(err => {
  console.error(err);
  process.exit(1);
});
