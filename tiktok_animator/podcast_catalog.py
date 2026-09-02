#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / 'tiktok_animator' / 'podcast_queue.json'
STATE_PATH = ROOT / 'tiktok_animator' / 'podcast_state.json'


def load(path):
    return json.loads(path.read_text())


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def run_json(args):
    p = subprocess.run(args, capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


def source_id(story):
    if story.get('source_id'):
        return str(story['source_id'])
    m = re.search(r'/video/([^/?#]+)', str(story.get('source_url', '')))
    return m.group(1) if m else None


def timestamp_parts(info):
    duration = float(info.get('duration') or 0)
    chapters = info.get('chapters') or []
    usable = []
    for ch in chapters:
        try:
            start = float(ch.get('start_time'))
            end = float(ch.get('end_time'))
        except (TypeError, ValueError):
            continue
        title = str(ch.get('title') or '').strip()
        if title and end > start:
            usable.append((start, end, title))
    if len(usable) >= 2:
        return [
            {'number': i + 1, 'label': label, 'start': round(start, 3), 'end': round(end, 3)}
            for i, (start, end, label) in enumerate(usable)
        ]

    desc = str(info.get('description') or '')
    marks = []
    rx = re.compile(r'(?m)^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s*[-–—:]?\s*(.+?)\s*$')
    for m in rx.finditer(desc):
        h = int(m.group(1) or 0)
        minute = int(m.group(2))
        sec = int(m.group(3))
        label = re.sub(r'^[•*\-–—]+\s*', '', m.group(4)).strip()
        start = h * 3600 + minute * 60 + sec
        if label and (not marks or start > marks[-1][0]):
            marks.append((float(start), label))
    if len(marks) < 2 or duration <= 0:
        raise RuntimeError(f"No reliable chapter/timestamp structure found for {info.get('title')}")
    parts = []
    for i, (start, label) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else duration
        if end > start:
            parts.append({'number': len(parts) + 1, 'label': label, 'start': round(start, 3), 'end': round(end, 3)})
    if len(parts) < 2:
        raise RuntimeError(f"Not enough reliable parts found for {info.get('title')}")
    return parts


def main():
    queue = load(QUEUE_PATH)
    state = load(STATE_PATH)
    stories = queue.get('stories') or []
    if not stories:
        raise RuntimeError('Podcast queue has no anchor story')

    idx = int(state.get('story_index', 0))
    if idx >= len(stories):
        idx = len(stories) - 1
    current = stories[idx]
    next_part = int(state.get('next_part', 1))

    # Only discover another story when the currently locked story is complete.
    if next_part <= len(current.get('parts') or []):
        print('Current story still has parts remaining; catalog unchanged.')
        return 0
    if idx + 1 < len(stories):
        print('Next story already queued.')
        return 0

    catalog_url = queue.get('show', {}).get('source_catalog_url') or 'https://www.dailymotion.com/user/MasterPOVYT/videos'
    listing = run_json(['yt-dlp', '--flat-playlist', '--dump-single-json', '--playlist-end', '300', catalog_url])
    entries = list(listing.get('entries') or [])
    if not entries:
        raise RuntimeError('Master POV source catalog returned no videos')

    # Dailymotion exposes newest first. Reverse so the queue advances oldest -> newest.
    entries.reverse()
    known_ids = {x for x in (source_id(s) for s in stories) if x}
    current_id = source_id(current)
    anchor_pos = None
    if current_id:
        for i, entry in enumerate(entries):
            if str(entry.get('id') or '') == current_id:
                anchor_pos = i
                break
    if anchor_pos is None:
        normalized = re.sub(r'\W+', ' ', str(current.get('title', '')).lower()).strip()
        for i, entry in enumerate(entries):
            title = re.sub(r'\W+', ' ', str(entry.get('title', '')).lower()).strip()
            if normalized and (normalized in title or title in normalized):
                anchor_pos = i
                break
    if anchor_pos is None:
        raise RuntimeError(f"Could not locate current story in source catalog: {current.get('title')}")

    chosen = None
    for entry in entries[anchor_pos + 1:]:
        eid = str(entry.get('id') or '')
        if eid and eid not in known_ids:
            chosen = entry
            break
    if not chosen:
        print('No newer unqueued Master POV story is available yet.')
        return 0

    eid = str(chosen.get('id'))
    url = str(chosen.get('url') or '')
    if not url.startswith('http'):
        url = f'https://www.dailymotion.com/video/{eid}'
    info = run_json(['yt-dlp', '--dump-single-json', '--no-playlist', url])
    parts = timestamp_parts(info)
    title = str(info.get('title') or chosen.get('title') or '').strip()
    if not title:
        raise RuntimeError('Discovered story has no title')

    upload_date = str(info.get('upload_date') or '')
    published = f'{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}' if len(upload_date) == 8 else None
    story = {
        'id': f'dm-{eid}',
        'source_id': eid,
        'title': title,
        'source_url': str(info.get('webpage_url') or url),
        'published': published,
        'parts': parts,
    }
    stories.append(story)
    queue['stories'] = stories
    save(QUEUE_PATH, queue)
    print(json.dumps({'queuedNextStory': title, 'sourceId': eid, 'parts': len(parts)}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
