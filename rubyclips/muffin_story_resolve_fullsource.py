#!/usr/bin/env python3
import json, math, subprocess
from pathlib import Path

BASE = Path('rubyclips')
WORK = BASE / 'muffin_work'
STATE_PATH = BASE / 'muffin_state.json'
CHUNK_SECONDS = 580.0
MIN_SOURCE_SECONDS = 900.0


def run(args, **kwargs):
    print('+', ' '.join(str(x) for x in args), flush=True)
    return subprocess.run(args, check=True, **kwargs)


def probe(url):
    try:
        out = subprocess.check_output([
            'yt-dlp', '--no-playlist', '--skip-download', '--dump-single-json',
            '--socket-timeout', '25', '--retries', '2', url
        ], text=True, stderr=subprocess.STDOUT, timeout=120)
        data = json.loads(out.strip().splitlines()[-1])
        duration = float(data.get('duration') or 0)
        return {
            'url': url,
            'id': str(data.get('id') or ''),
            'title': str(data.get('title') or ''),
            'duration': duration,
        }
    except Exception as exc:
        print(f'Probe failed for {url}: {exc}', flush=True)
        return None


def duration(path):
    return float(subprocess.check_output([
        'ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nw=1:nk=1',str(path)
    ], text=True).strip())


state = json.loads(STATE_PATH.read_text())
provider = str(state.get('sourceProvider') or '').lower()
if provider != 'dailymotion-muffindrama-mirror':
    raise SystemExit(f'Full-story resolver is not enabled for provider {provider!r}.')
if bool(state.get('currentSeriesComplete')):
    raise SystemExit('Current mirror-backed story is already complete.')

part = int(state.get('nextPart') or 1)
next_ep = int(state.get('nextEpisode') or part)
candidates = [str(x) for x in state.get('sourceCandidates', []) if str(x).startswith('https://www.dailymotion.com/video/')]
if not candidates:
    raise SystemExit('No Dailymotion source candidates configured.')

WORK.mkdir(parents=True, exist_ok=True)
for p in WORK.glob('ep*.mp4'):
    p.unlink(missing_ok=True)
for name in ['episodes.json','selected.json','concat.txt','continuation.json','source-cut.mp4','source-normalized.mp4']:
    (WORK / name).unlink(missing_ok=True)

probes = [x for x in (probe(url) for url in candidates) if x and x['duration'] >= MIN_SOURCE_SECONDS]
if not probes:
    raise SystemExit('No reachable long-form source candidate passed the duration check.')
# Prefer the longest reachable copy. This avoids accidentally selecting a teaser or partial upload.
chosen = max(probes, key=lambda x: x['duration'])
full_duration = chosen['duration']
story_total_parts = max(1, math.ceil(full_duration / CHUNK_SECONDS))
start = (part - 1) * CHUNK_SECONDS
if start >= full_duration - 2.0:
    raise SystemExit(f'No source content remains for Part {part}; source is {full_duration:.2f}s.')
clip_len = min(CHUNK_SECONDS, full_duration - start)
end = start + clip_len
story_complete = end >= full_duration - 2.0

raw_template = str(WORK / 'source-cut.%(ext)s')
section = f'*{start:.3f}-{end:.3f}'
try:
    run([
        'yt-dlp','--no-playlist','--no-progress','--socket-timeout','30','--retries','4',
        '--download-sections',section,'--force-keyframes-at-cuts',
        '-f','best[height<=720]/best','--merge-output-format','mp4',
        '-o',raw_template,chosen['url']
    ], timeout=1200)
except subprocess.CalledProcessError:
    run([
        'yt-dlp','--no-playlist','--no-progress','--socket-timeout','30','--retries','4',
        '--download-sections',section,'--force-keyframes-at-cuts',
        '-f','best','--merge-output-format','mp4',
        '-o',raw_template,chosen['url']
    ], timeout=1200)

raws = sorted(WORK.glob('source-cut.*'))
if not raws:
    raise SystemExit('yt-dlp did not create the requested source cut.')
raw = raws[0]
out = WORK / f'ep{next_ep}.mp4'
run([
    'ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(raw),
    '-map','0:v:0','-map','0:a:0','-c:v','libx264','-preset','veryfast','-crf','19',
    '-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(out)
], timeout=1200)
actual = duration(out)
if actual < 10 or actual > 598.5:
    raise SystemExit(f'Normalized source cut has invalid duration: {actual:.3f}s')
if out.stat().st_size < 500000:
    raise SystemExit(f'Normalized source cut is unexpectedly small: {out.stat().st_size} bytes')

item = {
    'episode': next_ep,
    'sourceUrl': chosen['url'],
    'shortDramaUrl': str(state.get('catalogUrl') or 'https://www.tiktok.com/@muffindrama_us'),
    'videoId': chosen['id'],
    'sourceHint': 'muffindrama-story-via-reachable-full-story-mirror',
    'sourceProvider': 'dailymotion-muffindrama-mirror',
    'sourceChannel': '@muffindrama_us',
    'file': str(out),
    'duration': actual,
}
(WORK / 'episodes.json').write_text(json.dumps([item], indent=2) + '\n')
continuation = {
    'sourceProvider': item['sourceProvider'],
    'sourceVideoId': chosen['id'],
    'sourceUrl': chosen['url'],
    'sourceTitle': chosen['title'],
    'part': part,
    'storyTotalParts': story_total_parts,
    'startSeconds': start,
    'endSeconds': min(end, full_duration),
    'fullDurationSeconds': full_duration,
    'storyComplete': story_complete,
    'nextEpisode': next_ep + 1,
}
(WORK / 'continuation.json').write_text(json.dumps(continuation, indent=2) + '\n')
print(json.dumps(continuation, indent=2))
