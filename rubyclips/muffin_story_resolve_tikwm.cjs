const { execFileSync } = require('child_process');
console.log('Using canonical MuffinDrama video IDs via yt-dlp; no TikTok episode-page navigation.');
execFileSync('node', ['rubyclips/muffin_story_resolve_ytdlp.cjs'], { stdio: 'inherit' });
