#!/usr/bin/env python3
import json, math, subprocess
from pathlib import Path

BASE = Path('rubyclips')
WORK = BASE / 'muffin_work'
STATE = BASE / 'muffin_state.json'
ALIGNMENT = BASE / 'dailymotion_alignment.json'
FULL = BASE / 'dm_full.mp4'
PART11 = BASE / 'dm_part11.mp4'
SOURCE_URL = 'https://www.dailymotion.com/video/xb2tc0i'
SOURCE_ID = 'xb2tc0i'
SERIES_ID = '7682993954661553173'
BASE_POSTED_PART = 11
CHUNK_SECONDS = 580.0


def run(args):
    print('+', ' '.join(str(x) for x in args), flush=True)
    subprocess.run(args, check=True)


def duration(path):
    return float(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=nw=1:nk=1', str(path)
    ], text=True).strip())


state = json.loads(STATE.read_text())
if str(state.get('currentSeriesId')) != SERIES_ID:
    raise SystemExit('Dailymotion continuation is locked to the current Rubaradaclips story only.')
part = int(state['nextPart'])
next_ep = int(state['nextEpisode'])
if part < 12:
    raise SystemExit(f'Dailymotion continuation should not run before Part 12 (got Part {part}).')

WORK.mkdir(parents=True, exist_ok=True)
for p in [FULL, PART11, ALIGNMENT, BASE / 'dm_full.raw', BASE / 'dm_part11.raw']:
    try:
        p.unlink()
    except FileNotFoundError:
        pass
for p in WORK.glob('ep*.mp4'):
    p.unlink(missing_ok=True)
for name in ['episodes.json', 'selected.json', 'concat.txt', 'continuation.json']:
    (WORK / name).unlink(missing_ok=True)

# Use the already-probed full-story copy. If its preferred HLS rendition changes,
# fall back to the best <=720p rendition rather than failing the queue.
try:
    run([
        'yt-dlp', '--no-playlist', '--no-progress', '-N', '16',
        '-f', 'hls-380', '--merge-output-format', 'mp4',
        '--remux-video', 'mp4', '-o', str(FULL), SOURCE_URL
    ])
except subprocess.CalledProcessError:
    run([
        'yt-dlp', '--no-playlist', '--no-progress', '-N', '16',
        '-f', 'best[height<=720]/best', '--merge-output-format', 'mp4',
        '--remux-video', 'mp4', '-o', str(FULL), SOURCE_URL
    ])

run([
    'curl', '-L', '--fail', '--retry', '4', '--retry-delay', '2',
    '-o', str(PART11),
    'https://github.com/RubysRealm/RubysRealm/releases/download/'
    'rubyclips-tt-7682993954661553173-r2-p11/'
    'muffindrama-7682993954661553173-r2-part-11.mp4'
])

# Reuse the two-window audio correlation check. It must pass before any fallback
# clip is allowed into the publishing pipeline.
run(['python', 'rubyclips/dailymotion_align.py'])
align = json.loads(ALIGNMENT.read_text())
if not align.get('alignmentAcceptable'):
    raise SystemExit('Dailymotion source did not pass continuity validation against Part 11.')

full_duration = float(align['fullDuration'])
base_start = float(align['part11EndInFull'])
start = base_start + (part - (BASE_POSTED_PART + 1)) * CHUNK_SECONDS
remaining = full_duration - start
if remaining <= 2.0:
    raise SystemExit(f'No usable story content remains at Part {part}: {remaining:.2f}s')
clip_len = min(CHUNK_SECONDS, remaining)
end = start + clip_len
story_complete = end >= full_duration - 2.0
remaining_after_part11 = max(0.0, full_duration - base_start)
story_total_parts = BASE_POSTED_PART + max(1, math.ceil(remaining_after_part11 / CHUNK_SECONDS))

out = WORK / f'ep{next_ep}.mp4'
run([
    'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
    '-ss', f'{start:.3f}', '-i', str(FULL), '-t', f'{clip_len:.3f}',
    '-map', '0:v:0', '-map', '0:a:0',
    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19',
    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000',
    '-movflags', '+faststart', str(out)
])
actual = duration(out)
if actual < 10 or actual > 598.5:
    raise SystemExit(f'Fallback clip duration is invalid: {actual:.3f}s')
if out.stat().st_size < 500000:
    raise SystemExit(f'Fallback clip is unexpectedly small: {out.stat().st_size} bytes')

item = {
    'episode': next_ep,
    'sourceUrl': SOURCE_URL,
    'shortDramaUrl': f'https://www.tiktok.com/shortdrama/episode/{SERIES_ID}/{next_ep}',
    'videoId': SOURCE_ID,
    'sourceHint': 'dailymotion-full-story-continuity-aligned',
    'sourceProvider': 'dailymotion',
    'sourceChannel': '@muffindrama_us',
    'file': str(out),
    'duration': actual,
}
(WORK / 'episodes.json').write_text(json.dumps([item], indent=2) + '\n')
continuation = {
    'sourceProvider': 'dailymotion',
    'sourceVideoId': SOURCE_ID,
    'sourceUrl': SOURCE_URL,
    'alignment': align,
    'part': part,
    'storyTotalParts': story_total_parts,
    'startSeconds': start,
    'endSeconds': min(end, full_duration),
    'fullDurationSeconds': full_duration,
    'storyComplete': story_complete,
    'nextEpisode': int(state['currentSeriesEpisodeCount']) + 1 if story_complete else next_ep + 1,
}
(WORK / 'continuation.json').write_text(json.dumps(continuation, indent=2) + '\n')
print(json.dumps(continuation, indent=2))
