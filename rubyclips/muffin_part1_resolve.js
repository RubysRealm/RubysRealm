const fs = require('fs');
const { execFileSync } = require('child_process');
const Tiktok = require('@tobyg74/tiktok-api-dl');

const episodes = [
  [1, 'https://www.tiktok.com/@muffindrama_us/video/7682997000391904526'],
  [2, 'https://www.tiktok.com/@muffindrama_us/video/7682997015172762893'],
  [3, 'https://www.tiktok.com/@muffindrama_us/video/7682996961800244494']
];

function media(r) {
  const v = r && r.result && r.result.video;
  if (typeof v === 'string') return v;
  if (v && typeof v.playAddr === 'string') return v.playAddr;
  if (v && Array.isArray(v.playAddr)) return v.playAddr[0];
  if (v && typeof v.downloadAddr === 'string') return v.downloadAddr;
  if (v && Array.isArray(v.downloadAddr)) return v.downloadAddr[0];
  return null;
}

(async () => {
  fs.mkdirSync('rubyclips/muffin_work', { recursive: true });
  const out = [];
  for (const [n, url] of episodes) {
    let r = await Tiktok.Downloader(url, { version: 'v2' });
    let src = media(r);
    if (!src) {
      r = await Tiktok.Downloader(url, { version: 'v1' });
      src = media(r);
    }
    if (!src) throw new Error(`Episode ${n}: no video URL`);
    const file = `rubyclips/muffin_work/ep${n}.mp4`;
    execFileSync('curl', ['-L', '--fail', '--retry', '2', '-A', 'Mozilla/5.0', '-e', 'https://www.tiktok.com/', src, '-o', file], { stdio: 'inherit' });
    if (fs.statSync(file).size < 100000) throw new Error(`Episode ${n}: download too small`);
    out.push({ episode: n, sourceUrl: url, videoId: url.split('/').pop(), file });
  }
  fs.writeFileSync('rubyclips/muffin_work/episodes.json', JSON.stringify(out, null, 2));
})().catch(e => { console.error(e); process.exit(1); });
