#!/usr/bin/env python3
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path('rubyclips')
WORK = BASE / 'muffin_work'
STATE = BASE / 'muffin_state.json'
CHANNEL_VIDEOS = 'https://www.youtube.com/@muffindrama-uvu/videos'
SOURCE_CHANNEL = '@muffindrama-uvu'
CHUNK_SECONDS = 595.0
HARD_MAX_SECONDS = 598.5
YT_FORMAT = '18/best[ext=mp4][vcodec^=avc1][acodec!=none][height<=720]/best[ext=mp4][acodec!=none][height<=720]/best[height<=720]'
EJS_ARGS = ['--js-runtimes', 'node', '--remote-components', 'ejs:github']


def run(args, **kwargs):
    print('+', ' '.join(str(x) for x in args), flush=True)
    return subprocess.run(args, check=True, **kwargs)


def output(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def duration(path):
    return float(output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)]))


def commit_state(message):
    run(['git', 'config', 'user.name', 'rubyclips-publisher-bot'])
    run(['git', 'config', 'user.email', 'actions@users.noreply.github.com'])
    run(['git', 'add', str(STATE)])
    diff = subprocess.run(['git', 'diff', '--cached', '--quiet'])
    if diff.returncode == 0:
        return
    run(['git', 'commit', '-m', message])
    run(['git', 'push'])


def list_channel_videos():
    # The public flat listing gives us stable IDs, titles and durations without
    # making a second per-video metadata request that can trigger a bot check.
    raw = output([
        'yt-dlp', '--flat-playlist', '--playlist-reverse', '--dump-single-json',
        *EJS_ARGS, CHANNEL_VIDEOS,
    ])
    data = json.loads(raw)
    entries = data.get('entries') or []
    cleaned = []
    for e in entries:
        vid = str(e.get('id') or '').strip()
        title = str(e.get('title') or '').strip()
        try:
            d = float(e.get('duration') or 0)
        except Exception:
            d = 0
        if not vid or not title:
            continue
        cleaned.append({
            'id': vid,
            'title': title,
            'url': f'https://www.youtube.com/watch?v={vid}',
            'duration': d,
        })
    if not cleaned:
        raise SystemExit('No videos were returned from the MuffinDrama YouTube channel.')
    return cleaned


def cleanup_download_targets(raw):
    raw.unlink(missing_ok=True)
    for p in WORK.glob('youtube-section-raw.*'):
        if p.is_file():
            p.unlink(missing_ok=True)


def section_command(video_url, section, raw, extractor_args):
    return [
        'yt-dlp', '--no-playlist', '--no-progress', '--no-warnings',
        '--retries', '20', '--fragment-retries', '20', '--retry-sleep', 'fragment:2',
        *EJS_ARGS,
        '--extractor-args', extractor_args,
        '--download-sections', section,
        '-f', YT_FORMAT,
        '--merge-output-format', 'mp4', '--remux-video', 'mp4',
        '-o', str(raw), video_url,
    ]


def bootstrap_bgutil():
    print('Direct EJS clients were challenged; bootstrapping a local PO-token provider.', flush=True)
    run([sys.executable, '-m', 'pip', 'install', '--quiet', '--upgrade', 'bgutil-ytdlp-pot-provider'])

    root = Path.home() / 'bgutil-ytdlp-pot-provider'
    try:
        version = output([
            sys.executable, '-c',
            "import importlib.metadata as m; print(m.version('bgutil-ytdlp-pot-provider'))",
        ])
    except Exception:
        version = ''

    if root.exists():
        shutil.rmtree(root)

    cloned = False
    if version:
        attempt = subprocess.run([
            'git', 'clone', '--depth', '1', '--single-branch', '--branch', version,
            'https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git', str(root),
        ])
        cloned = attempt.returncode == 0
        if not cloned and root.exists():
            shutil.rmtree(root)

    if not cloned:
        run([
            'git', 'clone', '--depth', '1',
            'https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git', str(root),
        ])

    server = root / 'server'
    run(['npm', 'ci', '--silent'], cwd=server)
    run(['npx', 'tsc'], cwd=server)
    if not (server / 'build').exists():
        raise RuntimeError('PO-token provider build did not produce server/build.')
    return server


def try_section_download(video_url, section, raw):
    # Current YouTube extraction needs EJS challenge solving. Try several
    # unauthenticated clients before adding the heavier PO-token provider.
    strategies = [
        ('ejs-tv-web-mweb', 'youtube:player_client=tv_downgraded,web_creator,mweb;formats=missing_pot,duplicate'),
        ('ejs-mweb', 'youtube:player_client=mweb;formats=missing_pot,duplicate'),
        ('ejs-web-embedded', 'youtube:player_client=web_embedded;formats=missing_pot,duplicate'),
    ]
    errors = []
    for name, extractor in strategies:
        cleanup_download_targets(raw)
        print(f'Trying YouTube acquisition strategy: {name}', flush=True)
        proc = subprocess.run(section_command(video_url, section, raw, extractor))
        if proc.returncode == 0 and raw.exists() and raw.stat().st_size >= 500000:
            return name
        errors.append(f'{name}: exit {proc.returncode}')

    server = bootstrap_bgutil()
    po_extractor = (
        'youtube:player_client=mweb;formats=missing_pot,duplicate'
        f';youtubepot-bgutilscript:server_home={server}'
    )
    # yt-dlp extractor args are scoped by extractor name. Pass the PO provider
    # separately so both youtube and youtubepot settings are applied.
    cleanup_download_targets(raw)
    cmd = [
        'yt-dlp', '--no-playlist', '--no-progress', '--no-warnings',
        '--retries', '20', '--fragment-retries', '20', '--retry-sleep', 'fragment:2',
        *EJS_ARGS,
        '--extractor-args', 'youtube:player_client=mweb;formats=missing_pot,duplicate',
        '--extractor-args', f'youtubepot-bgutilscript:server_home={server}',
        '--download-sections', section,
        '-f', YT_FORMAT,
        '--merge-output-format', 'mp4', '--remux-video', 'mp4',
        '-o', str(raw), video_url,
    ]
    print('Trying YouTube acquisition strategy: bgutil-po-token-mweb', flush=True)
    proc = subprocess.run(cmd)
    if proc.returncode == 0 and raw.exists() and raw.stat().st_size >= 500000:
        return 'bgutil-po-token-mweb'
    errors.append(f'bgutil-po-token-mweb: exit {proc.returncode}')
    raise RuntimeError('All YouTube acquisition strategies failed: ' + '; '.join(errors))


WORK.mkdir(parents=True, exist_ok=True)
for p in WORK.glob('ep*.mp4'):
    p.unlink(missing_ok=True)
for name in ['episodes.json', 'selected.json', 'concat.txt', 'continuation.json', 'youtube-section-raw.mp4']:
    (WORK / name).unlink(missing_ok=True)

state = json.loads(STATE.read_text())
provider = str(state.get('sourceProvider') or '').lower()
if state.get('currentSeriesComplete') is True or provider != 'youtube':
    completed = {str(x) for x in state.get('completedSeriesIds', [])}
    videos = list_channel_videos()
    info = next((v for v in videos if v['id'] not in completed), None)
    if not info:
        raise SystemExit('No uncompleted MuffinDrama YouTube stories remain.')
    if not (info['duration'] > 0):
        raise SystemExit(f'Channel listing did not expose duration for {info["id"]}; refusing to guess Part X of Y.')
    total_parts = max(1, math.ceil(info['duration'] / CHUNK_SECONDS))
    state.update({
        'sourceProvider': 'youtube',
        'sourceChannel': SOURCE_CHANNEL,
        'currentSeriesId': info['id'],
        'currentSeriesTitle': info['title'],
        'currentSeriesEpisodeCount': total_parts,
        'storyTotalParts': total_parts,
        'sourceDurationSeconds': round(info['duration'], 3),
        'youtubeSourceUrl': info['url'],
        'restartGeneration': 2,
        'nextEpisode': 1,
        'nextPart': 1,
        'lastPostedPart': 0,
        'lastPostedEpisodes': [],
        'currentSeriesComplete': False,
    })
    STATE.write_text(json.dumps(state, indent=2) + '\n')
    commit_state(f'Start MuffinDrama YouTube story {info["id"]} [skip ci]')
    print(f'Selected YouTube story: {info["title"]} ({info["id"]}), {info["duration"]:.2f}s, {total_parts} parts.', flush=True)

if str(state.get('sourceProvider') or '').lower() != 'youtube':
    raise SystemExit('YouTube resolver called while state is not configured for YouTube.')

video_id = str(state['currentSeriesId'])
video_url = str(state.get('youtubeSourceUrl') or f'https://www.youtube.com/watch?v={video_id}')
part = int(state['nextPart'])
total_parts = int(state.get('storyTotalParts') or state['currentSeriesEpisodeCount'])
source_duration = float(state.get('sourceDurationSeconds') or 0)
if source_duration <= 0:
    raise SystemExit('YouTube source duration is missing from state.')
start = (part - 1) * CHUNK_SECONDS
remaining = source_duration - start
if remaining <= 1:
    raise SystemExit(f'No source content remains for Part {part}.')
clip_len = min(CHUNK_SECONDS, remaining)
end = start + clip_len

raw = WORK / 'youtube-section-raw.mp4'
out = WORK / f'ep{part}.mp4'
section = f'*{start:.3f}-{end:.3f}'
source_strategy = try_section_download(video_url, section, raw)

if not raw.exists() or raw.stat().st_size < 500000:
    raise SystemExit('YouTube section download was unexpectedly small.')

run([
    'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(raw), '-t', f'{clip_len:.3f}',
    '-map', '0:v:0', '-map', '0:a:0?',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p',
    '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', str(out),
])
actual = duration(out)
if actual < 5 or actual > HARD_MAX_SECONDS:
    raise SystemExit(f'Prepared YouTube part duration is invalid: {actual:.3f}s')
if out.stat().st_size < 500000:
    raise SystemExit('Prepared YouTube part is unexpectedly small.')

item = {
    'episode': part,
    'sourceUrl': video_url,
    'shortDramaUrl': video_url,
    'videoId': video_id,
    'sourceHint': f'authorized-muffindrama-youtube:{source_strategy}',
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
    'sourceStrategy': source_strategy,
}, indent=2) + '\n')
print(json.dumps({
    'videoId': video_id,
    'part': part,
    'totalParts': total_parts,
    'duration': actual,
    'storyComplete': story_complete,
    'sourceStrategy': source_strategy,
}, indent=2))
