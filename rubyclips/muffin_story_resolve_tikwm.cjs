const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const BASE = 'rubyclips';
const WORK = path.join(BASE, 'muffin_work');
const STATE_PATH = path.join(BASE, 'muffin_state.json');
const LOOKAHEAD_EPISODES = 12;
const PACKING_TARGET_SECONDS = 590.0;
const AUTHOR = 'muffindrama_us';

// Canonical TikTok item IDs recovered from the MuffinDrama episode metadata.
const KNOWN_EPISODE_IDS = {
  40: '7682997059560951054',
  41: '7682997068738071822',
  42: '7682997027734621454',
  43: '7682997049444289805',
  44: '7682997046084685069',
  45: '7682997097267809550',
  46: '7682997091664235790',
  47: '7682997037314395406',
  48: '7682997041479388429',
  49: '7682997039516470542'
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

function durationOf(file) {
  return Number(execFileSync('ffprobe', ['-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1', file], { encoding: 'utf8' }).trim());
}

function hasAudio(file) {
  const out = execFileSync('ffprobe', ['-v','error','-select_streams','a','-show_entries','stream=index','-of','csv=p=0', file], { encoding: 'utf8' }).trim();
  return Boolean(out);
}

function collectUrls(value, out = []) {
  if (value == null) return out;
  if (typeof value === 'string') {
    const s = value.trim();
    if (/^(https?:)?\/\//i.test(s) || /^\//.test(s)) out.push(s);
    return out;
  }
  if (Array.isArray(value)) {
    for (const v of value) collectUrls(v, out);
    return out;
  }
  if (typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      if (/play|video|download|url|src|addr/i.test(k)) collectUrls(v, out);
      else if (typeof v === 'object') collectUrls(v, out);
    }
  }
  return out;
}

function normalizeCandidate(u) {
  if (!u) return null;
  let s = String(u).replace(/\\u002F/g, '/').replace(/&amp;/g, '&').trim();
  if (s.startsWith('//')) s = 'https:' + s;
  if (s.startsWith('/')) s = 'https://www.tikwm.com' + s;
  return /^https?:\/\//i.test(s) ? s : null;
}

async function tikwmCandidates(videoId) {
  const sourceUrl = `https://www.tiktok.com/@${AUTHOR}/video/${videoId}`;
  const endpoints = [
    `https://www.tikwm.com/api/?url=${encodeURIComponent(sourceUrl)}&hd=1`,
    `https://www.tikwm.com/api/?url=${encodeURIComponent(videoId)}&hd=1`
  ];
  const results = [];
  for (const endpoint of endpoints) {
    try {
      const r = await fetch(endpoint, {
        headers: {
          'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36',
          'accept': 'application/json,text/plain,*/*'
        },
        redirect: 'follow'
      });
      const text = await r.text();
      let j;
      try { j = JSON.parse(text); } catch { throw new Error(`non-JSON response ${r.status}: ${text.slice(0,120)}`); }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = j && (j.data || j.result || j);
      if (data && data.author && data.author.unique_id) {
        const uid = String(data.author.unique_id).toLowerCase();
        if (uid && !uid.includes('muffin')) throw new Error(`resolver returned wrong author ${uid}`);
      }
      const preferred = [data?.hdplay, data?.play, data?.wmplay, data?.video?.hdplay, data?.video?.play, data?.video?.playAddr];
      const raw = [...preferred, ...collectUrls(data)];
      for (const x of raw) {
        const n = normalizeCandidate(x);
        if (!n) continue;
        if (/cover|avatar|music|\.jpeg|\.jpg|\.png|\.webp/i.test(n)) continue;
        if (!results.includes(n)) results.push(n);
      }
      if (results.length) break;
    } catch (e) {
      console.error(`TikWM endpoint failed for ${videoId}: ${e.message}`);
    }
  }
  return { sourceUrl, candidates: results };
}

function tryDownload(candidate, file, referer) {
  const args = ['-L','--fail','--retry','2','--retry-delay','1','--connect-timeout','25','--max-time','180',
    '-A','Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36',
    '-e', referer, candidate, '-o', file];
  execFileSync('curl', args, { stdio: 'inherit' });
  const size = fs.existsSync(file) ? fs.statSync(file).size : 0;
  if (size < 500000) throw new Error(`downloaded file too small (${size} bytes)`);
  const dur = durationOf(file);
  if (!Number.isFinite(dur) || dur < 10) throw new Error(`invalid/placeholder duration ${dur}`);
  if (!hasAudio(file)) throw new Error('video has no audio stream');
  return dur;
}

async function resolveEpisode(episode) {
  const videoId = KNOWN_EPISODE_IDS[episode];
  if (!videoId) throw new Error(`Episode ${episode}: no canonical TikTok item ID mapped yet`);
  const { sourceUrl, candidates } = await tikwmCandidates(videoId);
  if (!candidates.length) throw new Error(`Episode ${episode}: TikWM returned no media candidates for ${videoId}`);
  const file = path.join(WORK, `ep${episode}.mp4`);
  let lastErr = null;
  for (const candidate of candidates.slice(0, 12)) {
    try {
      try { if (fs.existsSync(file)) fs.unlinkSync(file); } catch {}
      const dur = tryDownload(candidate, file, sourceUrl);
      console.log(`Resolved Episode ${episode} -> ${videoId} via TikWM ${dur.toFixed(2)}s`);
      return {
        episode,
        sourceUrl,
        shortDramaUrl: `https://www.tiktok.com/shortdrama/episode/${seriesId}/${episode}`,
        videoId,
        sourceHint: 'tikwm-direct-id',
        file,
        duration: dur
      };
    } catch (e) {
      lastErr = e;
      console.error(`Episode ${episode} candidate failed: ${e.message}`);
    }
  }
  try { if (fs.existsSync(file)) fs.unlinkSync(file); } catch {}
  throw new Error(`Episode ${episode}: all TikWM media candidates failed${lastErr ? `: ${lastErr.message}` : ''}`);
}

(async () => {
  const resolved = [];
  let packedSeconds = 0;
  const last = Math.min(episodeCount, firstEpisode + LOOKAHEAD_EPISODES - 1);
  for (let episode = firstEpisode; episode <= last; episode++) {
    let item;
    try { item = await resolveEpisode(episode); }
    catch (e) {
      if (episode === firstEpisode) throw e;
      console.error(`Stopping lookahead at Episode ${episode}: ${e.message}`);
      break;
    }
    if (resolved.length && packedSeconds + item.duration > PACKING_TARGET_SECONDS) {
      fs.unlinkSync(item.file);
      console.log(`Episode ${episode} would exceed ${PACKING_TARGET_SECONDS}s; Part ${state.nextPart} is full.`);
      break;
    }
    resolved.push(item);
    packedSeconds += item.duration;
    if (packedSeconds >= PACKING_TARGET_SECONDS) break;
  }
  if (!resolved.length || Number(resolved[0].episode) !== firstEpisode) {
    throw new Error(`Resolver did not produce required Episode ${firstEpisode}.`);
  }
  fs.writeFileSync(path.join(WORK, 'episodes.json'), JSON.stringify(resolved, null, 2) + '\n');
  console.log(`Prepared ${resolved.length} consecutive episodes starting at ${firstEpisode}; ${packedSeconds.toFixed(2)} seconds.`);
})().catch(err => { console.error(err); process.exit(1); });
