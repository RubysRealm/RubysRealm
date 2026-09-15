const fs = require('fs');
const { spawnSync, execFileSync } = require('child_process');

const state = JSON.parse(fs.readFileSync('rubyclips/muffin_state.json', 'utf8'));
const currentSeriesId = String(state.currentSeriesId || '');
const nextPart = Number(state.nextPart || 0);
const provider = String(state.sourceProvider || '').toLowerCase();

if (state.currentSeriesComplete === true || provider === 'youtube') {
  console.log('Using the MuffinDrama YouTube channel as the Rubaradaclips story source.');
  const fresh = spawnSync('python', ['rubyclips/youtube_story_resolve_websafari.py'], { stdio: 'inherit' });
  if (fresh.status !== 0) {
    console.log('tv+web_safari path was unavailable; falling back to the existing EJS/PO-token resolver.');
    execFileSync('python', ['rubyclips/youtube_story_resolve.py'], { stdio: 'inherit' });
  }
} else if (currentSeriesId === '7682993954661553173' && nextPart >= 12) {
  console.log('Using continuity-aligned full-story source for the remainder of the previous Rubaradaclips story.');
  execFileSync('python', ['rubyclips/muffin_story_resolve_dailymotion.py'], { stdio: 'inherit' });
} else {
  console.log('Using canonical MuffinDrama video IDs via yt-dlp.');
  execFileSync('node', ['rubyclips/muffin_story_resolve_ytdlp.cjs'], { stdio: 'inherit' });
}
