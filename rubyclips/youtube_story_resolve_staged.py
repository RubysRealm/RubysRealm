#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
from urllib.parse import quote

BASE = Path('rubyclips')
WORK = BASE / 'muffin_work'
STATE = BASE / 'muffin_state.json'
OWNER = 'RubysRealm'
REPO = 'RubysRealm'
HARD_MAX_SECONDS = 598.5
RENDER_SOURCE = 'https://rubyclips-phone-host.onrender.com/source'


def output(args):
    return subprocess.check_output(args, text=True).strip()


def duration(path):
    return float(output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)]))


WORK.mkdir(parents=True, exist_ok=True)
state = json.loads(STATE.read_text())
if str(state.get('sourceProvider') or '').lower() != 'youtube':
    raise SystemExit(2)

video_id = str(state['currentSeriesId'])
part = int(state['nextPart'])
total_parts = int(state.get('storyTotalParts') or state['currentSeriesEpisodeCount'])
source_duration = float(state.get('sourceDurationSeconds') or 0)
if source_duration <= 0:
    raise SystemExit(2)

asset = f'source-part-{part:02d}.mp4'
tag = f'rubyclips-source-{video_id}'
release_url = f'https://github.com/{OWNER}/{REPO}/releases/download/{quote(tag)}/{quote(asset)}'
render_url = f'{RENDER_SOURCE}/{quote(asset)}'
raw = WORK / f'staged-source-{part:02d}.mp4'
out = WORK / f'ep{part}.mp4'
raw.unlink(missing_ok=True)
out.unlink(missing_ok=True)

source_strategy = None
for label, url in [
    ('render-auth-bridge', render_url),
    ('staged-auth-browser', release_url),
]:
    raw.unlink(missing_ok=True)
    print(f'Trying authenticated source ({label}): {url}', flush=True)
    proc = subprocess.run(['curl', '-fL', '--retry', '3', '--connect-timeout', '15', '--max-time', '180', '-o', str(raw), url])
    if proc.returncode == 0 and raw.exists() and raw.stat().st_size >= 500000:
        source_strategy = label
        break

if source_strategy is None:
    raise SystemExit(3)

expected_start = (part - 1) * 595.0
remaining = source_duration - expected_start
clip_len = min(595.0, remaining)
if clip_len <= 1:
    raise SystemExit(4)

subprocess.run([
    'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(raw), '-t', f'{clip_len:.3f}',
    '-map', '0:v:0', '-map', '0:a:0?',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', str(out)
], check=True)
actual = duration(out)
if actual < 5 or actual > HARD_MAX_SECONDS or out.stat().st_size < 500000:
    raise SystemExit(f'Authenticated source produced invalid part duration: {actual:.3f}s')

video_url = str(state.get('youtubeSourceUrl') or f'https://www.youtube.com/watch?v={video_id}')
item = {
    'episode': part,
    'sourceUrl': video_url,
    'shortDramaUrl': video_url,
    'videoId': video_id,
    'sourceHint': f'authorized-muffindrama-youtube:{source_strategy}',
    'sourceProvider': 'youtube',
    'sourceChannel': state.get('sourceChannel') or '@muffindrama-uvu',
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
    'startSeconds': round(expected_start, 3),
    'endSeconds': round(min(expected_start + clip_len, source_duration), 3),
    'fullDurationSeconds': round(source_duration, 3),
    'storyComplete': story_complete,
    'nextEpisode': total_parts + 1 if story_complete else part + 1,
    'sourceStrategy': source_strategy,
}, indent=2) + '\n')
print(json.dumps({'ok': True, 'videoId': video_id, 'part': part, 'totalParts': total_parts, 'duration': actual, 'sourceStrategy': source_strategy}, indent=2))
