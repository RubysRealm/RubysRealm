#!/usr/bin/env python3
import json
import subprocess
import urllib.request
from pathlib import Path

BASE = Path('rubyclips')
WORK = BASE / 'muffin_work'
STATE = BASE / 'muffin_state.json'
SOURCE_CHANNEL = '@muffindrama-uvu'
COBALT_API = 'https://rubyclips-cobalt-3.onrender.com/'
CHUNK_SECONDS = 595.0
HARD_MAX_SECONDS = 598.5


def output(args):
    return subprocess.check_output(args, text=True).strip()


def duration(path):
    return float(output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)]))


def resolve(url):
    payload = json.dumps({
        'url': url,
        'videoQuality': '720',
        'youtubeVideoCodec': 'h264',
        'downloadMode': 'auto',
        'alwaysProxy': True,
    }).encode('utf-8')
    req = urllib.request.Request(
        COBALT_API,
        data=payload,
        method='POST',
        headers={'Accept': 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'rubyclips-source/1.0'},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode('utf-8', 'replace'))
    if data.get('status') not in ('tunnel', 'redirect') or not str(data.get('url') or '').startswith('http'):
        raise RuntimeError(f'Cobalt did not return usable media: {data}')
    return str(data['url'])


WORK.mkdir(parents=True, exist_ok=True)
state = json.loads(STATE.read_text())
if str(state.get('sourceProvider') or '').lower() != 'youtube':
    raise SystemExit(2)
video_id = str(state['currentSeriesId'])
video_url = str(state.get('youtubeSourceUrl') or f'https://www.youtube.com/watch?v={video_id}')
part = int(state['nextPart'])
total_parts = int(state.get('storyTotalParts') or state['currentSeriesEpisodeCount'])
source_duration = float(state.get('sourceDurationSeconds') or 0)
start = (part - 1) * CHUNK_SECONDS
remaining = source_duration - start
if remaining <= 1:
    raise SystemExit(2)
clip_len = min(CHUNK_SECONDS, remaining)
end = start + clip_len
raw = WORK / 'youtube-cobalt-section.mp4'
out = WORK / f'ep{part}.mp4'
raw.unlink(missing_ok=True)
out.unlink(missing_ok=True)

print(f'Resolving authorized MuffinDrama source through Cobalt: video={video_id} part={part}/{total_parts}', flush=True)
media_url = resolve(video_url)

# The Cobalt tunnel proxies the media while hiding the short-lived upstream URL.
# Fast input seek keeps each automation run to only the requested ~10-minute part.
cmd = [
    'ffmpeg', '-y', '-hide_banner', '-loglevel', 'warning',
    '-ss', f'{start:.3f}', '-i', media_url, '-t', f'{clip_len:.3f}',
    '-map', '0:v:0', '-map', '0:a:0?',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', str(raw),
]
subprocess.run(cmd, check=True)
if not raw.exists() or raw.stat().st_size < 500000:
    raise SystemExit(3)

# Normalize once more into the exact builder input shape and clamp any timestamp tail.
subprocess.run([
    'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(raw), '-t', f'{clip_len:.3f}',
    '-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', str(out)
], check=True)
actual = duration(out)
if actual < 5 or actual > HARD_MAX_SECONDS or out.stat().st_size < 500000:
    raise SystemExit(f'Cobalt source produced invalid part duration: {actual:.3f}s')

item = {
    'episode': part,
    'sourceUrl': video_url,
    'shortDramaUrl': video_url,
    'videoId': video_id,
    'sourceHint': 'muffindrama-youtube:cobalt-trusted-session',
    'sourceProvider': 'youtube',
    'sourceChannel': SOURCE_CHANNEL,
    'file': str(out),
    'duration': actual,
}
(WORK / 'episodes.json').write_text(json.dumps([item], indent=2) + '\n')
story_complete = part >= total_parts
(WORK / 'continuation.json').write_text(json.dumps({
    'sourceProvider': 'youtube',
    'sourceVideoId': video_id,
    'sourceUrl': video_url,
    'storyTotalParts': total_parts,
    'part': part,
    'startSeconds': round(start, 3),
    'endSeconds': round(min(end, source_duration), 3),
    'fullDurationSeconds': round(source_duration, 3),
    'storyComplete': story_complete,
    'nextEpisode': total_parts + 1 if story_complete else part + 1,
    'sourceStrategy': 'cobalt-trusted-session',
}, indent=2) + '\n')
print(json.dumps({'ok': True, 'videoId': video_id, 'part': part, 'totalParts': total_parts, 'duration': actual, 'sourceStrategy': 'cobalt-trusted-session'}, indent=2))
