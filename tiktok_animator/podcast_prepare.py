#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / 'tiktok_animator' / 'podcast_queue.json'
STATE_PATH = ROOT / 'tiktok_animator' / 'podcast_state.json'
OUT = ROOT / 'tiktok_animator' / 'podcast_output'
TZ = ZoneInfo('America/New_York')


def load(path): return json.loads(path.read_text())
def save(path, data): path.write_text(json.dumps(data, indent=2) + '\n')


def active_part(queue, state):
    today = datetime.now(TZ).date().isoformat()
    stories = queue['stories']
    idx = int(state.get('story_index', 0))
    if idx >= len(stories): return None, None, None
    story = stories[idx]
    next_part = int(state.get('next_part', 1))
    if state.get('story_day') is None:
        state['story_day'] = today
        save(STATE_PATH, state)
    if next_part > len(story['parts']):
        if today == state.get('story_day'):
            print('Current story completed; next story waits until tomorrow.')
            return None, None, None
        idx += 1
        if idx >= len(stories):
            print('No next story queued yet.')
            return None, None, None
        state.update({'story_index': idx, 'next_part': 1, 'story_day': today, 'last_publish_id': None, 'last_published_at': None})
        save(STATE_PATH, state)
        story = stories[idx]
        next_part = 1
    return story, story['parts'][next_part - 1], len(story['parts'])


def cadence_ready(queue, state):
    last = state.get('last_published_at')
    if not last: return True
    hours = float(queue.get('show', {}).get('cadence_hours', 1))
    remaining = timedelta(hours=hours) - (datetime.now(TZ) - datetime.fromisoformat(last))
    if remaining.total_seconds() > 0:
        print(f'Cadence lock active for another {int(remaining.total_seconds()//60)+1} minutes.')
        return False
    return True


def download(url, work):
    template = str(work / 'source.%(ext)s')
    subprocess.run(['yt-dlp','--no-playlist','--merge-output-format','mp4','-f','bv*+ba/b','-o',template,url], check=True)
    files = sorted(work.glob('source.*'))
    if not files: raise RuntimeError('Source video download produced no file')
    return files[0]


def duration(path):
    p = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],capture_output=True,text=True,check=True)
    return float(p.stdout.strip())


def render(source, part, output):
    start, end = float(part['start']), float(part['end'])
    vf=(
      '[0:v]split=2[bg][fg];'
      '[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=24[bg2];'
      '[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg2];'
      '[bg2][fg2]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]'
    )
    subprocess.run(['ffmpeg','-y','-v','error','-ss',f'{start:.3f}','-to',f'{end:.3f}','-i',str(source),'-filter_complex',vf,'-map','[v]','-map','0:a?','-c:v','libx264','-preset','medium','-crf','20','-r','30','-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)],check=True)
    if not output.exists() or output.stat().st_size < 100000: raise RuntimeError('Rendered part missing or too small')


def main():
    queue, state = load(QUEUE_PATH), load(STATE_PATH)
    if not cadence_ready(queue, state): return 0
    story, part, total = active_part(queue, state)
    if story is None: return 0
    expected = int(state.get('next_part', 1))
    if int(part['number']) != expected: raise RuntimeError(f'Ordering lock failed: expected {expected}, got {part["number"]}')
    OUT.mkdir(parents=True, exist_ok=True)
    for p in OUT.iterdir():
        if p.is_file(): p.unlink()
    with tempfile.TemporaryDirectory(prefix='rubys-podcast-') as td:
        source = download(story['source_url'], Path(td))
        filename = f"{story['id']}-part-{expected:02d}.mp4"
        video = OUT / filename
        render(source, part, video)
    manifest = {
      'platform':'rubys-realm-podcast-repost-v1',
      'storyId':story['id'],
      'title':story['title'],
      'partNumber':expected,
      'totalParts':total,
      'partLabel':part['label'],
      'durationSeconds':round(duration(video),3),
      'file':filename,
      'sourceUrl':story['source_url'],
      'preparedAt':datetime.now(TZ).isoformat()
    }
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as e:
        print(e,file=sys.stderr); sys.exit(1)
