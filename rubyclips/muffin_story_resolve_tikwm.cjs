const fs = require('fs');
const { spawnSync, execFileSync } = require('child_process');

const state = JSON.parse(fs.readFileSync('rubyclips/muffin_state.json', 'utf8'));
const currentSeriesId = String(state.currentSeriesId || '');
const nextPart = Number(state.nextPart || 0);
const provider = String(state.sourceProvider || '').toLowerCase();

if (provider === 'spotify-show') {
  console.log('Using the user-provided Spotify show as the Rubaradaclips source catalog.');
  execFileSync('python', ['rubyclips/spotify_story_resolve.py'], { stdio: 'inherit' });
} else if (provider === 'dailymotion-muffindrama-mirror') {
  console.log('Using reachable long-form transport for the selected MuffinDrama story.');
  execFileSync('python', ['rubyclips/muffin_story_resolve_fullsource.py'], { stdio: 'inherit' });
} else if (provider === 'youtube') {
  console.log('Using the MuffinDrama YouTube channel as the Rubaradaclips story source.');
  const cobalt = spawnSync('python', ['rubyclips/youtube_story_resolve_cobalt.py'], { stdio: 'inherit' });
  if (cobalt.status === 0) {
    console.log('Using Cobalt trusted-session MuffinDrama source part.');
  } else {
    const staged = spawnSync('python', ['rubyclips/youtube_story_resolve_staged.py'], { stdio: 'inherit' });
    if (staged.status === 0) {
      console.log('Using staged authenticated MuffinDrama source part.');
    } else {
      console.log('Cobalt and staged source were unavailable; trying direct YouTube paths.');
      const fresh = spawnSync('python', ['rubyclips/youtube_story_resolve_websafari.py'], { stdio: 'inherit' });
      if (fresh.status !== 0) {
        console.log('tv+web_safari path was unavailable; falling back to the existing EJS/PO-token resolver.');
        execFileSync('python', ['rubyclips/youtube_story_resolve.py'], { stdio: 'inherit' });
      }
    }
  }
} else if (currentSeriesId === '7682993954661553173' && nextPart >= 12) {
  console.log('Using continuity-aligned full-story source for the remainder of the previous Rubaradaclips story.');
  execFileSync('python', ['rubyclips/muffin_story_resolve_dailymotion.py'], { stdio: 'inherit' });
} else {
  console.log('Using canonical MuffinDrama video IDs via yt-dlp.');
  execFileSync('node', ['rubyclips/muffin_story_resolve_ytdlp.cjs'], { stdio: 'inherit' });
}
