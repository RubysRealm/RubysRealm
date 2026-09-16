import { spawn, spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const VIDEO_ID = process.env.YOUTUBE_VIDEO_ID || '5-bO9NAhWbI';
const VIDEO_URL = process.env.YOUTUBE_SOURCE_URL || `https://www.youtube.com/watch?v=${VIDEO_ID}`;
const TOTAL_PARTS = Number(process.env.STORY_TOTAL_PARTS || 11);
const SEGMENT_SECONDS = Number(process.env.SEGMENT_SECONDS || 595);
const SOURCE_DURATION = Number(process.env.SOURCE_DURATION_SECONDS || 6372);
const SOURCE_DIR = '/tmp/rubyclips-source';
const PROFILE = '/tmp/youtube-browser';
const FULL = path.join(SOURCE_DIR, 'full.mp4');
const STATUS = path.join(SOURCE_DIR, 'status.json');

fs.mkdirSync(SOURCE_DIR, { recursive: true });

function writeStatus(extra = {}) {
  let prior = {};
  try { prior = JSON.parse(fs.readFileSync(STATUS, 'utf8')); } catch {}
  const readyParts = [];
  for (let i = 1; i <= TOTAL_PARTS; i++) {
    const name = `source-part-${String(i).padStart(2, '0')}.mp4`;
    const file = path.join(SOURCE_DIR, name);
    if (fs.existsSync(file) && fs.statSync(file).size > 250000) readyParts.push(i);
  }
  const state = {
    videoId: VIDEO_ID,
    sourceUrl: VIDEO_URL,
    totalParts: TOTAL_PARTS,
    segmentSeconds: SEGMENT_SECONDS,
    sourceDurationSeconds: SOURCE_DURATION,
    signedIn: false,
    downloading: false,
    stage: 'waiting_for_login',
    readyParts,
    updatedAt: new Date().toISOString(),
    ...prior,
    ...extra,
    readyParts
  };
  fs.writeFileSync(STATUS, JSON.stringify(state, null, 2));
}

function run(cmd, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: ['ignore', 'inherit', 'inherit'], ...opts });
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`)));
  });
}

function probeLogin() {
  const r = spawnSync('yt-dlp', [
    '--cookies-from-browser', `chrome+basictext:${PROFILE}`,
    '--no-playlist', '--skip-download', '--no-warnings', '--print', '%(id)s', VIDEO_URL
  ], { encoding: 'utf8', timeout: 90000 });
  return r.status === 0 && String(r.stdout || '').trim().split(/\s+/).includes(VIDEO_ID);
}

async function downloadFull() {
  writeStatus({ signedIn: true, downloading: true, stage: 'downloading_source', error: null });
  for (const f of fs.readdirSync(SOURCE_DIR)) {
    if (f.startsWith('full.') && f !== 'full.mp4') try { fs.unlinkSync(path.join(SOURCE_DIR, f)); } catch {}
  }
  await run('yt-dlp', [
    '--cookies-from-browser', `chrome+basictext:${PROFILE}`,
    '--no-playlist', '--retries', '20', '--fragment-retries', '20',
    '--concurrent-fragments', '4',
    '-f', 'bv*[height<=720]+ba/b[height<=720]/best',
    '--merge-output-format', 'mp4', '--remux-video', 'mp4',
    '-o', path.join(SOURCE_DIR, 'full.%(ext)s'), VIDEO_URL
  ]);
  const candidates = fs.readdirSync(SOURCE_DIR)
    .filter(x => x.startsWith('full.') && /\.(mp4|mkv|webm|mov)$/i.test(x))
    .map(x => path.join(SOURCE_DIR, x));
  if (!candidates.length) throw new Error('yt-dlp completed but no source file was created');
  const selected = candidates.sort((a,b) => fs.statSync(b).size - fs.statSync(a).size)[0];
  if (selected !== FULL) {
    await run('ffmpeg', ['-y','-hide_banner','-loglevel','error','-i',selected,'-c','copy','-movflags','+faststart',FULL]);
    try { fs.unlinkSync(selected); } catch {}
  }
  if (!fs.existsSync(FULL) || fs.statSync(FULL).size < 1000000) throw new Error('Downloaded source is unexpectedly small');
}

async function splitParts() {
  writeStatus({ signedIn: true, downloading: true, stage: 'splitting_source' });
  for (let part = 1; part <= TOTAL_PARTS; part++) {
    const out = path.join(SOURCE_DIR, `source-part-${String(part).padStart(2, '0')}.mp4`);
    if (fs.existsSync(out) && fs.statSync(out).size > 250000) continue;
    const start = (part - 1) * SEGMENT_SECONDS;
    const remaining = Math.max(0, SOURCE_DURATION - start);
    const len = Math.min(SEGMENT_SECONDS, remaining);
    if (len <= 0.5) break;
    const tmp = out + '.tmp.mp4';
    try { fs.unlinkSync(tmp); } catch {}
    await run('ffmpeg', [
      '-y','-hide_banner','-loglevel','error','-ss',String(start),'-i',FULL,'-t',String(len),
      '-map','0:v:0','-map','0:a:0?','-c','copy','-avoid_negative_ts','make_zero','-movflags','+faststart',tmp
    ]);
    fs.renameSync(tmp, out);
    writeStatus({ signedIn: true, downloading: true, stage: `part_${part}_ready` });
  }
  const manifest = {
    sourceProvider: 'youtube-auth-browser',
    sourceChannel: '@muffindrama-uvu',
    videoId: VIDEO_ID,
    sourceUrl: VIDEO_URL,
    durationSeconds: SOURCE_DURATION,
    totalParts: TOTAL_PARTS,
    segmentSeconds: SEGMENT_SECONDS,
    sessionRetainedExternally: false,
    createdAt: new Date().toISOString()
  };
  fs.writeFileSync(path.join(SOURCE_DIR, 'source-manifest.json'), JSON.stringify(manifest, null, 2));
  writeStatus({ signedIn: true, downloading: false, stage: 'ready', error: null });
}

async function main() {
  writeStatus({ stage: 'waiting_for_login', signedIn: false, downloading: false, error: null });
  while (!probeLogin()) {
    await new Promise(r => setTimeout(r, 5000));
  }
  writeStatus({ stage: 'login_confirmed', signedIn: true, downloading: false, error: null });
  try {
    await downloadFull();
    await splitParts();
  } catch (error) {
    writeStatus({ signedIn: true, downloading: false, stage: 'error', error: String(error?.message || error) });
    process.exitCode = 1;
  }
}

main();
