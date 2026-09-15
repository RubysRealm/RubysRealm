const fs = require('fs');
const { execFileSync } = require('child_process');

const state = JSON.parse(fs.readFileSync('rubyclips/muffin_state.json', 'utf8'));
const currentSeriesId = String(state.currentSeriesId || '');
const nextPart = Number(state.nextPart || 0);

// The TikTok episode endpoints for this exact story became unstable after Part 11.
// Keep every other story on the normal MuffinDrama resolver, but finish this story
// from the full-story source after a continuity check against the already-posted Part 11.
if (currentSeriesId === '7682993954661553173' && nextPart >= 12) {
  console.log('Using continuity-aligned full-story source for the remainder of the current Rubaradaclips story.');
  execFileSync('python', ['rubyclips/muffin_story_resolve_dailymotion.py'], { stdio: 'inherit' });
} else {
  console.log('Using canonical MuffinDrama video IDs via yt-dlp; no TikTok episode-page navigation.');
  execFileSync('node', ['rubyclips/muffin_story_resolve_ytdlp.cjs'], { stdio: 'inherit' });
}
