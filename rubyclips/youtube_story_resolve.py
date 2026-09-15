#!/usr/bin/env python3
import json, math, subprocess
from pathlib import Path

BASE = Path('rubyclips')
WORK = BASE / 'muffin_work'
STATE = BASE / 'muffin_state.json'
CHANNEL_VIDEOS = 'https://www.youtube.com/@muffindrama-uvu/videos'
SOURCE_CHANNEL = '@muffindrama-uvu'
CHUNK_SECONDS = 595.0
HARD_MAX_SECONDS = 598.5
YT_EXTRACTOR = ['--extractor-args','youtube:player_client=android_vr;formats=missing_pot,duplicate']
YT_FORMAT = '18/best[ext=mp4][vcodec^=avc1][acodec!=none][height<=720]/best[ext=mp4][acodec!=none][height<=720]/best[height<=720]'


def run(args, **kwargs):
    print('+', ' '.join(str(x) for x in args), flush=True)
    return subprocess.run(args, check=True, **kwargs)


def output(args):
    return subprocess.check_output(args, text=True).strip()


def duration(path):
    return float(output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]))


def commit_state(message):
    run(['git','config','user.name','rubyclips-publisher-bot'])
    run(['git','config','user.email','actions@users.noreply.github.com'])
    run(['git','add',str(STATE)])
    diff = subprocess.run(['git','diff','--cached','--quiet'])
    if diff.returncode == 0:
        return
    run(['git','commit','-m',message])
    run(['git','push'])


def list_channel_videos():
    raw = output(['yt-dlp','--flat-playlist','--playlist-reverse','--dump-single-json',CHANNEL_VIDEOS])
    data = json.loads(raw)
    entries = data.get('entries') or []
    cleaned = []
    for e in entries:
        vid = str(e.get('id') or '').strip()
        title = str(e.get('title') or '').strip()
        if not vid or not title:
            continue
        cleaned.append({'id': vid, 'title': title, 'url': f'https://www.youtube.com/watch?v={vid}'})
    if not cleaned:
        raise SystemExit('No videos were returned from the MuffinDrama YouTube channel.')
    return cleaned


def detailed_video(video):
    raw = output(['yt-dlp','--no-playlist','--skip-download','--dump-single-json',*YT_EXTRACTOR,video['url']])
    info = json.loads(raw)
    d = float(info.get('duration') or 0)
    title = str(info.get('title') or video['title']).strip()
    if d <= 0:
        raise SystemExit(f'Could not determine duration for {video["url"]}')
    return {'id': video['id'], 'title': title, 'url': video['url'], 'duration': d}


WORK.mkdir(parents=True, exist_ok=True)
for p in WORK.glob('ep*.mp4'):
    p.unlink(missing_ok=True)
for name in ['episodes.json','selected.json','concat.txt','continuation.json','youtube-section-raw.mp4']:
    (WORK / name).unlink(missing_ok=True)

state = json.loads(STATE.read_text())
provider = str(state.get('sourceProvider') or '').lower()
if state.get('currentSeriesComplete') is True or provider != 'youtube':
    completed = {str(x) for x in state.get('completedSeriesIds', [])}
    videos = list_channel_videos()
    next_video = next((v for v in videos if v['id'] not in completed), None)
    if not next_video:
        raise SystemExit('No uncompleted MuffinDrama YouTube stories remain.')
    info = detailed_video(next_video)
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
    print(f'Selected YouTube story: {info["title"]} ({info["id"]}), {total_parts} parts.', flush=True)

if str(state.get('sourceProvider') or '').lower() != 'youtube':
    raise SystemExit('YouTube resolver called while state is not configured for YouTube.')

video_id = str(state['currentSeriesId'])
video_url = str(state.get('youtubeSourceUrl') or f'https://www.youtube.com/watch?v={video_id}')
part = int(state['nextPart'])
total_parts = int(state.get('storyTotalParts') or state['currentSeriesEpisodeCount'])
source_duration = float(state.get('sourceDurationSeconds') or 0)
if source_duration <= 0:
    source_duration = detailed_video({'id': video_id, 'title': state['currentSeriesTitle'], 'url': video_url})['duration']
start = (part - 1) * CHUNK_SECONDS
remaining = source_duration - start
if remaining <= 1:
    raise SystemExit(f'No source content remains for Part {part}.')
clip_len = min(CHUNK_SECONDS, remaining)
end = start + clip_len

raw = WORK / 'youtube-section-raw.mp4'
out = WORK / f'ep{part}.mp4'
section = f'*{start:.3f}-{end:.3f}'
run([
    'yt-dlp','--no-playlist','--no-progress','--no-warnings','--retries','20','--fragment-retries','20','--retry-sleep','fragment:2',
    *YT_EXTRACTOR,'--download-sections',section,'-f',YT_FORMAT,
    '--merge-output-format','mp4','--remux-video','mp4','-o',str(raw),video_url
])
if not raw.exists() or raw.stat().st_size < 500000:
    raise SystemExit('YouTube section download was unexpectedly small.')

run([
    'ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(raw),'-t',f'{clip_len:.3f}',
    '-map','0:v:0','-map','0:a:0?',
    '-c:v','libx264','-preset','ultrafast','-crf','22','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(out)
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
    'sourceHint': 'authorized-muffindrama-youtube',
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
}, indent=2) + '\n')
print(json.dumps({'videoId': video_id, 'part': part, 'totalParts': total_parts, 'duration': actual, 'storyComplete': story_complete}, indent=2))
