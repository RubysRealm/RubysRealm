const fs = require('fs');
const { execFileSync } = require('child_process');

const episodes = [
  {episode:1, sourceUrl:'https://www.tiktok.com/@muffindrama_us/video/7682997000391904526', videoId:'7682997000391904526', media:'https://tikcdn.io/ssstik/7682997000391904526?st=kHFDcVVhXnGRJxxmtXnXAg&e=1789343795'},
  {episode:2, sourceUrl:'https://www.tiktok.com/@muffindrama_us/video/7682997015172762893', videoId:'7682997015172762893', media:'https://tikcdn.io/ssstik/7682997015172762893?st=5Rp-Y2DtUhCw4vmk9-_11w&e=1789343713'},
  {episode:3, sourceUrl:'https://www.tiktok.com/@muffindrama_us/video/7682996961800244494', videoId:'7682996961800244494', media:'https://tikcdn.io/ssstik/7682996961800244494?st=2fHkjcQgS26t2xxefGKRQQ&e=1789343747'}
];

fs.mkdirSync('rubyclips/muffin_work', { recursive: true });
const out = [];
for (const ep of episodes) {
  const file = `rubyclips/muffin_work/ep${ep.episode}.mp4`;
  execFileSync('curl', ['-L','--fail','--retry','2','--connect-timeout','20','-A','Mozilla/5.0', ep.media, '-o', file], { stdio: 'inherit' });
  if (fs.statSync(file).size < 100000) throw new Error(`Episode ${ep.episode}: download too small`);
  out.push({ episode: ep.episode, sourceUrl: ep.sourceUrl, videoId: ep.videoId, file });
}
fs.writeFileSync('rubyclips/muffin_work/episodes.json', JSON.stringify(out, null, 2));
