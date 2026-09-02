#!/usr/bin/env python3
import json
import os
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
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


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


def extract_part_audio(source, start, end, output):
    length = end - start
    subprocess.run([
        'ffmpeg','-y','-v','error','-ss',f'{start:.3f}','-t',f'{length:.3f}','-i',str(source),
        '-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(output)
    ], check=True)
    if not output.exists() or output.stat().st_size < 1000:
        raise RuntimeError('Could not extract narration audio for captions')


def ass_time(seconds):
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f'{h}:{m:02d}:{s:05.2f}'


def ass_escape(text):
    return text.replace('\\', r'\\').replace('{', r'\{').replace('}', r'\}').replace('\n', ' ')


def write_synced_captions(audio, ass_path):
    from faster_whisper import WhisperModel

    model_name = os.environ.get('WHISPER_MODEL', 'small.en').strip() or 'small.en'
    model = WhisperModel(model_name, device='cpu', compute_type='int8')
    segments_gen, _ = model.transcribe(
        str(audio),
        language='en',
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=True,
    )
    segments = list(segments_gen)

    timed_words = []
    for segment in segments:
        for word in (segment.words or []):
            text = (word.word or '').strip()
            if text and word.start is not None and word.end is not None:
                timed_words.append({'text': text, 'start': float(word.start), 'end': float(word.end)})

    entries = []
    current = []

    def flush():
        nonlocal current
        if not current:
            return
        text = ' '.join(w['text'] for w in current).strip()
        entries.append((current[0]['start'], current[-1]['end'] + 0.04, text))
        current = []

    for word in timed_words:
        if current and word['start'] - current[-1]['end'] > 0.48:
            flush()
        current.append(word)
        token = word['text']
        if len(current) >= 5 or (len(current) >= 3 and token.endswith(('.', '!', '?', ',', ';', ':'))):
            flush()
    flush()

    if not entries:
        for segment in segments:
            text = (segment.text or '').strip()
            if text:
                entries.append((float(segment.start), float(segment.end), text))

    if not entries:
        raise RuntimeError('Speech transcription returned no captions; refusing to publish an uncaptioned part')

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Captions,DejaVu Sans,68,&H00FFFFFF,&H00FFFFFF,&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,5,1,2,80,80,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for start, end, text in entries:
        lines.append(f'Dialogue: 0,{ass_time(start)},{ass_time(end)},Captions,,0,0,0,,{ass_escape(text)}\n')
    ass_path.write_text(''.join(lines), encoding='utf-8')
    print(f'Generated {len(entries)} narration-synced caption events with {model_name}.')


def render(source, part, total, captions, output):
    start, end = float(part['start']), float(part['end'])
    length = end - start
    if length <= 0:
        raise RuntimeError(f'Bad part range: {start}..{end}')

    part_text = f'PART {int(part["number"])}/{int(total)}'
    subtitle_path = str(captions).replace('\\', '/').replace("'", r"\'")
    vf=(
      '[0:v]split=2[bg][fg];'
      '[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=24[bg2];'
      '[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg2];'
      '[bg2][fg2]overlay=(W-w)/2:(H-h)/2[base];'
      f"[base]drawtext=fontfile={FONT}:text='{part_text}':fontcolor=white:fontsize=58:borderw=4:bordercolor=black@0.85:box=1:boxcolor=black@0.38:boxborderw=18:x=(w-text_w)/2:y=115[labeled];"
      f"[labeled]subtitles='{subtitle_path}',format=yuv420p[v]"
    )
    subprocess.run([
        'ffmpeg','-y','-v','error','-ss',f'{start:.3f}','-t',f'{length:.3f}','-i',str(source),
        '-filter_complex',vf,'-map','[v]','-map','0:a?','-c:v','libx264','-preset','medium','-crf','20','-r','30',
        '-c:a','aac','-b:a','192k','-movflags','+faststart',str(output)
    ],check=True)
    if not output.exists() or output.stat().st_size < 100000:
        raise RuntimeError('Rendered part missing or too small')


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
        work = Path(td)
        source = download(story['source_url'], work)
        start, end = float(part['start']), float(part['end'])
        audio = work / 'narration.wav'
        captions = work / 'captions.ass'
        extract_part_audio(source, start, end, audio)
        write_synced_captions(audio, captions)
        filename = f"{story['id']}-part-{expected:02d}.mp4"
        video = OUT / filename
        render(source, part, total, captions, video)
    manifest = {
      'platform':'rubys-realm-podcast-repost-v2',
      'storyId':story['id'],
      'title':story['title'],
      'partNumber':expected,
      'totalParts':total,
      'partLabel':part['label'],
      'partLabelBurnedIn':True,
      'captionsBurnedIn':True,
      'captionTiming':'word-timestamped narration transcription',
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
