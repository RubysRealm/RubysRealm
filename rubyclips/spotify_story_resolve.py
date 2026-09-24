#!/usr/bin/env python3
import difflib
import html
import json
import math
import re
import subprocess
import urllib.request
from pathlib import Path

BASE = Path('rubyclips')
WORK = BASE / 'muffin_work'
STATE_PATH = BASE / 'muffin_state.json'
COBALT_API = 'https://rubyclips-cobalt-3.onrender.com/'
CHUNK_SECONDS = 580.0
HARD_MAX_SECONDS = 598.5
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36'


def run(args, **kwargs):
    print('+', ' '.join(str(x) for x in args), flush=True)
    return subprocess.run(args, check=True, **kwargs)


def output(args):
    return subprocess.check_output(args, text=True).strip()


def media_duration(path):
    return float(output([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=nw=1:nk=1', str(path)
    ]))


def normalize_title(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value).lower()).strip()


def similarity(a, b):
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml',
    })
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode('utf-8', 'replace')


def spotify_episode_meta(episode_id, fallback_title, fallback_creator):
    page = fetch(f'https://open.spotify.com/embed/episode/{episode_id}')
    title = fallback_title
    creator = fallback_creator
    m = re.search(r'<title[^>]*>(.*?)</title>', page, re.I | re.S)
    if m:
        raw = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        suffix = re.match(r'^(.*?)\s+-\s+(.+?)\s+\\|\s+Spotify\s*$', raw)
        if suffix:
            title = suffix.group(1).strip() or title
            creator = suffix.group(2).strip() or creator
        else:
            title = re.sub(r'\s*\\|\s*Spotify\s*$', '', raw).strip() or title

    image = None
    for pattern in (
        r'https://image-cdn-[^"\\\']+spotifycdn\.com/image/[A-Za-z0-9]+',
        r'https://i\.scdn\.co/image/[A-Za-z0-9]+',
    ):
        m = re.search(pattern, page)
        if m:
            image = html.unescape(m.group(0))
            break
    return title, creator, image


def yt_channel_candidates(handle):
    handle = str(handle or '').strip().lstrip('@')
    if not handle:
        return []
    url = f'https://www.youtube.com/@{handle}/videos'
    cmd = [
        'yt-dlp', '--flat-playlist', '--playlist-end', '80', '--dump-json', '--no-warnings',
        '--socket-timeout', '25', '--retries', '3',
        '--js-runtimes', 'node', '--remote-components', 'ejs:github',
        url
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    if not rows:
        print('Creator channel listing returned no entries:', proc.stdout[-1200:], flush=True)
    return rows


def yt_search_candidates(query):
    cmd = [
        'yt-dlp', '--skip-download', '--dump-json', '--no-warnings',
        '--socket-timeout', '25', '--retries', '3',
        '--js-runtimes', 'node', '--remote-components', 'ejs:github',
        f'ytsearch8:{query}'
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
    rows = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def probe_transport(url):
    cmd = [
        'yt-dlp', '--skip-download', '--dump-single-json', '--no-warnings',
        '--socket-timeout', '25', '--retries', '3',
        '--js-runtimes', 'node', '--remote-components', 'ejs:github',
        '--extractor-args', 'youtube:player_client=tv,web_safari',
        url
    ]
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    lines = [x.strip() for x in proc.stdout.splitlines() if x.strip().startswith('{')]
    if not lines:
        return {}
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        return {}


def choose_transport(title, creator, channel_handle):
    # Search both the pinned creator channel and normal YouTube discovery.
    # The old flow stopped at the pinned channel whenever it returned any rows,
    # even if none of those rows matched the Spotify episode title.
    channel_rows = yt_channel_candidates(channel_handle)
    search_rows = yt_search_candidates(f'{title} {creator}'.strip())
    if not search_rows:
        search_rows = yt_search_candidates(title)

    rows = []
    seen = set()
    for row in channel_rows + search_rows:
        key = str(row.get('id') or row.get('webpage_url') or row.get('url') or '')
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        rows.append(row)

    if not rows:
        raise RuntimeError('No public media matches were found for the Spotify episode title.')

    creator_n = normalize_title(creator)
    handle_n = normalize_title(channel_handle)
    scored = []
    for row in rows:
        row_title = str(row.get('title') or '')
        uploader = ' '.join(str(row.get(k) or '') for k in ('uploader', 'channel', 'channel_id', 'uploader_id'))
        title_score = similarity(title, row_title)
        uploader_n = normalize_title(uploader)
        creator_match = bool(
            (creator_n and creator_n in uploader_n) or
            (handle_n and handle_n in uploader_n)
        )
        duration = float(row.get('duration') or 0)
        url = str(row.get('webpage_url') or row.get('url') or '')
        video_id = str(row.get('id') or '')
        if video_id and (not url.startswith('http') or 'youtube.com' not in url):
            url = f'https://www.youtube.com/watch?v={video_id}'
        if not url.startswith('http'):
            continue
        scored.append((creator_match, title_score, duration, row, url))

    if not scored:
        raise RuntimeError('Creator channel returned no usable public media transport.')
    scored.sort(key=lambda x: (x[1], x[0], x[2]), reverse=True)
    creator_match, title_score, duration, row, url = scored[0]
    if title_score < 0.72 or (creator and not creator_match and title_score < 0.94):
        raise RuntimeError(
            f'Refusing uncertain media match for Spotify episode. '
            f'Best title={row.get("title")!r}, uploader={row.get("uploader") or row.get("channel")!r}, score={title_score:.3f}'
        )

    detail = {}
    if duration < 15 or not row.get('thumbnail'):
        detail = probe_transport(url)
        duration = float(detail.get('duration') or duration or 0)
    if duration < 15:
        raise RuntimeError(f'Matched creator video has no usable duration: {url}')

    return {
        'url': url,
        'id': str(detail.get('id') or row.get('id') or ''),
        'title': str(detail.get('title') or row.get('title') or title),
        'thumbnail': str(detail.get('thumbnail') or row.get('thumbnail') or ''),
        'duration': duration,
        'uploader': str(detail.get('uploader') or detail.get('channel') or row.get('uploader') or row.get('channel') or creator),
        'matchScore': title_score,
    }

def cobalt_media(url):
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


def copy_cover(url):
    if not url:
        return None
    dest = WORK / 'story-cover.jpg'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=45) as resp:
        dest.write_bytes(resp.read())
    if dest.stat().st_size < 10000:
        dest.unlink(missing_ok=True)
        return None
    return str(dest)


def make_cut(transport, start, clip_len, out):
    raw = WORK / 'spotify-source-cut.mp4'
    raw.unlink(missing_ok=True)
    out.unlink(missing_ok=True)

    try:
        media_url = cobalt_media(transport['url'])
        run([
            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'warning',
            '-ss', f'{start:.3f}', '-i', media_url, '-t', f'{clip_len:.3f}',
            '-map', '0:v:0', '-map', '0:a:0?',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', str(raw)
        ], timeout=1800)
        strategy = 'spotify-catalog:cobalt-public-transport'
    except Exception as exc:
        print(f'Cobalt transport unavailable, falling back to direct public source: {exc}', flush=True)
        section = f'*{start:.3f}-{start + clip_len:.3f}'
        run([
            'yt-dlp', '--no-playlist', '--no-progress', '--retries', '12', '--fragment-retries', '12',
            '--retry-sleep', 'fragment:2', '--js-runtimes', 'node', '--remote-components', 'ejs:github',
            '--extractor-args', 'youtube:player_client=tv,web_safari',
            '--add-header', 'Referer:https://www.youtube.com/',
            '--add-header', 'Origin:https://www.youtube.com',
            '--download-sections', section,
            '-f', '18/best[ext=mp4][vcodec^=avc1][acodec!=none][height<=720]/best[ext=mp4][acodec!=none][height<=720]/best[height<=720]',
            '--merge-output-format', 'mp4', '--remux-video', 'mp4',
            '-o', str(raw), transport['url']
        ], timeout=1800)
        strategy = 'spotify-catalog:youtube-tv-web_safari'

    if not raw.exists() or raw.stat().st_size < 500000:
        raise RuntimeError('Media transport did not create a usable source cut.')

    run([
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-i', str(raw), '-t', f'{clip_len:.3f}',
        '-map', '0:v:0', '-map', '0:a:0',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', str(out)
    ], timeout=1800)
    return strategy


state = json.loads(STATE_PATH.read_text())
if str(state.get('sourceProvider') or '').lower() != 'spotify-show':
    raise SystemExit('Spotify resolver is not enabled for the current provider.')

WORK.mkdir(parents=True, exist_ok=True)
for pattern in ('ep*.mp4', 'story-cover.*', 'spotify-source-cut.*'):
    for p in WORK.glob(pattern):
        if p.is_file():
            p.unlink(missing_ok=True)
for name in ('episodes.json', 'selected.json', 'concat.txt', 'continuation.json', 'story-cover-intro.mp4'):
    (WORK / name).unlink(missing_ok=True)

episode_id = str(state.get('currentSeriesId') or '').strip()
if not episode_id:
    raise SystemExit('Current Spotify episode id is missing.')
spotify_url = str(state.get('spotifyEpisodeUrl') or f'https://open.spotify.com/episode/{episode_id}')
fallback_title = str(state.get('currentSeriesTitle') or '').strip()
fallback_creator = str(state.get('spotifyCreator') or state.get('sourceChannel') or '').strip().lstrip('@')

try:
    title, creator, spotify_image = spotify_episode_meta(episode_id, fallback_title, fallback_creator)
except Exception as exc:
    print(f'Could not refresh Spotify episode metadata; using queued metadata: {exc}', flush=True)
    title, creator, spotify_image = fallback_title, fallback_creator, None
if not title:
    raise SystemExit('Spotify episode title is unavailable.')

channel_handle = str(state.get('youtubeChannelHandle') or 'babynojamie')
transport = choose_transport(title, creator, channel_handle)
full_duration = float(transport['duration'])
part = int(state.get('nextPart') or 1)
next_ep = int(state.get('nextEpisode') or part)
story_total_parts = max(1, math.ceil(full_duration / CHUNK_SECONDS))
start = (part - 1) * CHUNK_SECONDS
if start >= full_duration - 2.0:
    raise SystemExit(f'No source content remains for Part {part}; source is {full_duration:.2f}s.')
clip_len = min(CHUNK_SECONDS, full_duration - start)
end = start + clip_len
story_complete = end >= full_duration - 2.0

cover_file = None
for cover_url in (spotify_image, transport.get('thumbnail')):
    try:
        cover_file = copy_cover(cover_url)
        if cover_file:
            break
    except Exception as exc:
        print(f'Cover fetch failed: {exc}', flush=True)

out = WORK / f'ep{next_ep}.mp4'
strategy = make_cut(transport, start, clip_len, out)
actual = media_duration(out)
if actual < 10 or actual > HARD_MAX_SECONDS:
    raise SystemExit(f'Normalized Spotify source cut has invalid duration: {actual:.3f}s')
if out.stat().st_size < 500000:
    raise SystemExit(f'Normalized Spotify source cut is unexpectedly small: {out.stat().st_size} bytes')

item = {
    'episode': next_ep,
    'sourceUrl': spotify_url,
    'shortDramaUrl': spotify_url,
    'videoId': episode_id,
    'sourceHint': strategy,
    'sourceProvider': 'spotify-show',
    'sourceChannel': creator or fallback_creator or 'spotify',
    'file': str(out),
    'duration': actual,
    'transportUrl': transport['url'],
    'transportVideoId': transport['id'],
}
if cover_file:
    item['coverFile'] = cover_file
(WORK / 'episodes.json').write_text(json.dumps([item], indent=2) + '\n')

continuation = {
    'sourceProvider': 'spotify-show',
    'sourceVideoId': episode_id,
    'sourceUrl': spotify_url,
    'sourceTitle': title,
    'sourceThumbnailUrl': spotify_image or transport.get('thumbnail') or None,
    'sourceCoverFile': cover_file,
    'mediaTransportUrl': transport['url'],
    'mediaTransportVideoId': transport['id'],
    'mediaTransportUploader': transport['uploader'],
    'mediaMatchScore': round(float(transport['matchScore']), 4),
    'sourceStrategy': strategy,
    'part': part,
    'storyTotalParts': story_total_parts,
    'startSeconds': round(start, 3),
    'endSeconds': round(min(end, full_duration), 3),
    'fullDurationSeconds': round(full_duration, 3),
    'storyComplete': story_complete,
    'nextEpisode': next_ep + 1,
}
(WORK / 'continuation.json').write_text(json.dumps(continuation, indent=2) + '\n')
print(json.dumps(continuation, indent=2))
