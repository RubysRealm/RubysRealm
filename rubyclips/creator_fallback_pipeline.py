#!/usr/bin/env python3
import asyncio
import importlib.util
import json
import math
import re
import shutil
from pathlib import Path

from yt_dlp import YoutubeDL

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STATE_PATH = HERE / 'facebook_state.json'
WORK = HERE / 'facebook_work'
OUT = HERE / 'facebook_output'
CHANNEL_URL = 'https://www.youtube.com/@bushcraftinthewildforest/videos'
CHANNEL_HANDLE = '@bushcraftinthewildforest'
MAX_SECONDS = 585.0

SPEC = importlib.util.spec_from_file_location('rubyclips_facebook_pipeline', HERE / 'facebook_pipeline.py')
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

# This is the story already completed on @rubaradaclips and must never be
# selected again if the same footage appears through the creator-feed fallback.
COMPLETED_TITLE_FRAGMENTS = [
    'building a warm and cozy forest house with a clay stove',
]


def norm_title(value):
    text = re.sub(r'\s+', ' ', str(value or '')).strip().lower()
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def display_title(value):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    text = re.sub(r'\s*@bushcraftinthewildforest\b', '', text, flags=re.I).strip(' -|')
    text = base.scrub_engagement_metadata(text)
    if not text or base.looks_like_engagement_metadata(text):
        text = 'Bushcraft Story'
    if len(text) > 76:
        text = text[:73].rstrip(' ,.;:-') + '…'
    lines = base.textwrap.wrap(text, width=31, break_long_words=False, break_on_hyphens=False)
    return '\n'.join(lines[:2]) if lines else 'Bushcraft Story'


def list_channel_entries():
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'playlistend': 80,
        'socket_timeout': 45,
        'retries': 3,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(CHANNEL_URL, download=False)
    entries = []
    for e in (info or {}).get('entries') or []:
        vid = str(e.get('id') or '').strip()
        title = str(e.get('title') or '').strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{6,20}', vid):
            continue
        if not title:
            continue
        entries.append({'id': vid, 'title': title, 'url': f'https://www.youtube.com/watch?v={vid}'})
    if not entries:
        raise RuntimeError('Configured YouTube channel returned no usable videos.')
    return entries


def full_metadata(entry):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 45,
        'retries': 3,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(entry['url'], download=False)
    if not info:
        raise RuntimeError('No creator-feed metadata returned.')
    return {
        'id': str(info.get('id') or entry['id']),
        'url': str(info.get('webpage_url') or entry['url']),
        'title': str(info.get('title') or entry['title']).strip(),
        'description': str(info.get('description') or '').strip(),
        'timestamp': int(info.get('timestamp') or info.get('release_timestamp') or 0),
        'upload_date': str(info.get('upload_date') or ''),
        'duration': float(info.get('duration') or 0),
    }


def download(meta):
    template = str(WORK / 'source.%(ext)s')
    opts = {
        'format': 'bv*+ba/b',
        'merge_output_format': 'mp4',
        'outtmpl': template,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': True,
        'socket_timeout': 60,
        'retries': 4,
        'fragment_retries': 4,
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([meta['url']])
    files = [f for f in WORK.glob('source.*') if f.is_file()]
    if not files:
        raise RuntimeError('Creator-feed download produced no file.')
    return max(files, key=lambda f: f.stat().st_size)


def caption(title, index, total):
    one_line = str(title).replace('\n', ' ').strip()
    text = f'{one_line} — {base.part_label(index, total)} #rubyclips #storytime #storytok'
    return text[:2200].strip()


def choose_entry(entries, posted, progress):
    # If a multipart creator-feed story has started, finish it before selecting
    # another source. Otherwise preserve the project's oldest-to-newest policy.
    for source_id in progress:
        for e in entries:
            if e['id'] == source_id and source_id not in posted:
                return e

    eligible = []
    for e in entries:
        if e['id'] in posted:
            continue
        nt = norm_title(e['title'])
        if any(fragment in nt for fragment in COMPLETED_TITLE_FRAGMENTS):
            continue
        eligible.append(e)
    if not eligible:
        raise RuntimeError('No unposted videos remain on the configured YouTube channel.')
    return eligible[-1]


async def main():
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    posted = {str(x) for x in state.get('creatorFallbackPostedVideoIds', [])}
    progress = {str(k): int(v) for k, v in (state.get('creatorFallbackSegmentProgress') or {}).items()}

    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    entries = list_channel_entries()
    chosen_entry = choose_entry(entries, posted, progress)
    meta = full_metadata(chosen_entry)

    src = download(meta)
    actual_duration = base.probe_duration(src)
    if actual_duration <= 0:
        raise RuntimeError('Creator-feed source duration is invalid.')

    total = max(1, int(math.ceil(actual_duration / MAX_SECONDS)))
    index = max(1, progress.get(meta['id'], 1))
    if index > total:
        index = 1

    start = (index - 1) * MAX_SECONDS
    remaining = max(0.1, actual_duration - start)
    length = min(MAX_SECONDS, remaining)
    title = display_title(meta['title'])
    part = base.part_label(index, total)

    if total == 1:
        final = OUT / f'creator-{meta["id"]}.mp4'
    else:
        final = OUT / f'creator-{meta["id"]}-segment-{index:02d}-of-{total:02d}.mp4'

    base.burn_layout(src, final, title, part, start=start, length=length)
    produced_duration = base.probe_duration(final)
    if produced_duration > 599.0:
        raise RuntimeError(f'Produced TikTok segment is too long: {produced_duration:.2f}s')
    if final.stat().st_size < 100000:
        raise RuntimeError('Produced creator-feed MP4 is unexpectedly small.')

    manifest = {
        'platform': 'rubyclips-creator-feed-v1',
        'sourceProvider': 'youtube',
        'sourceChannel': CHANNEL_HANDLE,
        'sourceChannelUrl': CHANNEL_URL,
        'sourceVideoId': meta['id'],
        'sourceUrl': meta['url'],
        'sourceTimestamp': meta.get('timestamp') or None,
        'sourceUploadDate': meta.get('upload_date') or None,
        'sourceDurationSeconds': round(actual_duration, 3),
        'segmentIndex': index,
        'segmentTotal': total,
        'segmentStartSeconds': round(start, 3),
        'segmentDurationSeconds': round(produced_duration, 3),
        'originalTitle': meta['title'],
        'displayTitle': title.replace('\n', ' '),
        'partLabel': part,
        'caption': caption(title, index, total),
        'file': final.name,
        'targetChannel': 'rubaradaclips',
        'technicalSplitOnly': total > 1,
        'titleBurnedIn': True,
        'partLabelBurnedIn': True,
        'overlayLayoutVersion': 'title-metadata-filtered-v3',
        'fallbackReason': 'configured-user-youtube-channel'
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
