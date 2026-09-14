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
const SERIES_FIRST_VIDEO_ID = '7682997000391904526';
const KNOWN_EPISODE_IDS = {
  1: '7682997000391904526',
  4: '7682996946042297620'
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
  if (/^ep\d+\.mp4$/.test(name) || ['episodes.json','selected.json','concat.txt','series-posts.json'].includes(name)) {
    try { fs.unlinkSync(path.join(WORK, name)); } catch {}
  }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const chrome = ['/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'].find(p => fs.existsSync(p));
let seriesPosts = null;

async function resolveMedia(videoId, episode, sourceHint = 'candidate') {
  const sourceUrl = `https://www.tiktok.com/@${AUTHOR}/video/${videoId}`;
  for (let attempt = 1; attempt <= 4; attempt++) {
    try {
      const result = await Tiktok.Downloader(sourceUrl, { version: 'v2' });
      const media = result?.result?.video?.playAddr?.[0];
      const nickname = String(result?.result?.author?.nickname || '').toLowerCase();
      if (result?.status === 'success' && media && (!nickname || nickname.includes('muffin'))) {
        return {
          episode,
          sourceUrl,
          shortDramaUrl: `https://www.tiktok.com/shortdrama/episode/${seriesId}/${episode}`,
          videoId: String(videoId),
          media,
          sourceHint
        };
      }
    } catch (e) {
      if (attempt === 4) console.error(`Episode ${episode}, ${videoId}: ${e.message}`);
    }
    await sleep(1000 * attempt);
  }
  return null;
}

async function loadSeriesPosts() {
  if (seriesPosts) return seriesPosts;
  try {
    console.log('Fetching MuffinDrama creator posts to recover the full 50-episode sequence...');
    const response = await Tiktok.GetUserPosts(AUTHOR, { postLimit: 1000 });
    if (response?.status !== 'success' || !Array.isArray(response.result) || !response.result.length) {
      throw new Error(response?.message || 'GetUserPosts returned no posts');
    }

    const posts = response.result
      .filter(p => p && p.id && p.video)
      .map(p => ({
        id: String(p.id),
        desc: String(p.desc || '').trim(),
        createTime: Number(p.createTime || 0),
        username: String(p.author?.username || '')
      }))
      .sort((a, b) => (a.createTime - b.createTime) || a.id.localeCompare(b.id));

    const start = posts.findIndex(p => p.id === SERIES_FIRST_VIDEO_ID);
    if (start < 0) throw new Error(`Could not find confirmed Episode 1 ID ${SERIES_FIRST_VIDEO_ID} in creator posts`);

    seriesPosts = posts.slice(start, start + episodeCount);
    if (!seriesPosts.length) throw new Error('Confirmed series slice is empty');
    fs.writeFileSync(path.join(WORK, 'series-posts.json'), JSON.stringify(seriesPosts, null, 2) + '\n');
    console.log(`Recovered ${seriesPosts.length} sequential creator posts beginning at confirmed Episode 1.`);
    return seriesPosts;
  } catch (e) {
    console.error(`Creator-post sequence lookup unavailable: ${e.message}`);
    seriesPosts = [];
    return seriesPosts;
  }
}

function collectVideoIds(text) {
  if (!text) return [];
  const out = [];
  const s = String(text);
  const patterns = [
    new RegExp(`@${AUTHOR}\\/video\\/(\\d{10,25})`, 'gi'),
    /["'](?:aweme_id|awemeId|itemId|item_id|videoId|video_id|group_id|groupId)["']\s*[:=]\s*["']?(\d{10,25})/gi
  ];
  for (const re of patterns) for (const m of s.matchAll(re)) out.push(m[1]);
  return [...new Set(out)];
}

async function browserFallback(episode) {
  if (!chrome) return null;
  const browser = await puppeteer.launch({
    headless: true,
    executablePath: chrome,
    args: ['--no-sandbox','--disable-dev-shm-usage']
  });
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
    await sleep(12000);
    const pageData = await page.evaluate(() => ({
      location: location.href,
      canonical: document.querySelector('link[rel="canonical"]')?.href || '',
      og: document.querySelector('meta[property="og:url"]')?.content || '',
      html: document.documentElement?.outerHTML || '',
      scripts: [...document.scripts].map(s => s.textContent || '').join('\n'),
      resources: performance.getEntriesByType('resource').map(x => x.name)
    }));
    capture(pageData.location);
    capture(pageData.canonical);
    capture(pageData.og);
    capture(pageData.html);
    capture(pageData.scripts);
    for (const r of pageData.resources) capture(r);
    await page.close();

    for (const id of captured.slice(0, 30)) {
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
  const posts = await loadSeriesPosts();
  const indexed = posts[episode - 1];
  if (indexed?.id) {
    const expectedLabel = String(episode);
    const labelLooksRight = !indexed.desc || indexed.desc === expectedLabel || new RegExp(`(^|\\D)${episode}(\\D|$)`).test(indexed.desc);
    if (!labelLooksRight) console.log(`Episode ${episode}: sequence post description is '${indexed.desc}', still validating by confirmed series position.`);
    const resolved = await resolveMedia(indexed.id, episode, 'creator-sequence');
    if (resolved) return resolved;
  }

  const known = KNOWN_EPISODE_IDS[episode];
  if (known) {
    const resolved = await resolveMedia(known, episode, 'known-id');
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
    try {
      item = await identifyEpisodeVideo(episode);
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
    resolved.push({ episode, sourceUrl: item.sourceUrl, shortDramaUrl: item.shortDramaUrl, videoId: item.videoId, sourceHint: item.sourceHint, file });
    console.log(`Resolved Episode ${episode} -> ${item.videoId} (${item.sourceHint})`);
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
