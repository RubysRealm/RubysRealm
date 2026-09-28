#!/usr/bin/env python3
import json, math, re, subprocess
from pathlib import Path

BASE=Path('rubyclips')
WORK=BASE/'muffin_work'
STATE=BASE/'muffin_state.json'
SOURCE_URL='https://www.facebook.com/100092703608304/posts/981343818299063/'
CHUNK_SECONDS=580.0
EXPECTED_TITLE='reading your MOST honest stories and playing minecraft'

def norm(s):
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',str(s or '').lower())).strip()

def run(args,timeout=1800):
    print('+',' '.join(map(str,args)),flush=True)
    subprocess.run(args,check=True,timeout=timeout)

def duration(path):
    return float(subprocess.check_output([
        'ffprobe','-v','error','-show_entries','format=duration',
        '-of','default=nw=1:nk=1',str(path)
    ],text=True).strip())

state=json.loads(STATE.read_text())
if state.get('currentSeriesId')!='2m4ncEaJmzwA9ucqrACTOH':
    raise SystemExit('This isolated build probe is locked to the oldest queued BabyJamie episode.')
if int(state.get('nextPart') or 1)!=1:
    raise SystemExit('This isolated build probe only builds Part 1.')

WORK.mkdir(parents=True,exist_ok=True)
for p in WORK.glob('ep*.mp4'): p.unlink(missing_ok=True)
for p in WORK.glob('story-cover.*'): p.unlink(missing_ok=True)
for name in ['episodes.json','selected.json','continuation.json','source-cut.mp4','story-cover-intro.mp4','story-title.txt','part-label.txt']:
    (WORK/name).unlink(missing_ok=True)

meta_raw=subprocess.check_output([
    'yt-dlp','--no-playlist','--skip-download','--dump-single-json',
    '--socket-timeout','30','--retries','3',SOURCE_URL
],text=True,stderr=subprocess.STDOUT,timeout=180)
meta=json.loads(meta_raw.strip().splitlines()[-1])
source_title=str(meta.get('title') or '')
full_duration=float(meta.get('duration') or 0)
source_id=str(meta.get('id') or '981343818299063')
thumb=str(meta.get('thumbnail') or '')
if norm(EXPECTED_TITLE) not in norm(source_title) and norm(source_title) not in norm(EXPECTED_TITLE):
    raise SystemExit(f'Public-copy title mismatch: {source_title!r}')
if not (2700 <= full_duration <= 2900):
    raise SystemExit(f'Unexpected full duration for oldest episode: {full_duration:.3f}s')

story_total_parts=max(1,math.ceil(full_duration/CHUNK_SECONDS))
start=0.0
end=min(CHUNK_SECONDS,full_duration)

# Grab artwork for the title card when available.
try:
    run([
        'yt-dlp','--no-playlist','--skip-download','--write-thumbnail',
        '--convert-thumbnails','jpg','--socket-timeout','30','--retries','3',
        '-o',str(WORK/'story-cover.%(ext)s'),SOURCE_URL
    ],timeout=240)
except Exception as exc:
    print('Cover fetch failed; builder will continue without it:',exc,flush=True)

raw=WORK/'source-cut.mp4'
run([
    'yt-dlp','--no-playlist','--no-progress','--socket-timeout','30','--retries','4',
    '--download-sections',f'*{start:.3f}-{end:.3f}','--force-keyframes-at-cuts',
    '-f','bestvideo*+bestaudio/best','--merge-output-format','mp4',
    '-o',str(raw),SOURCE_URL
],timeout=2400)
if not raw.exists() or raw.stat().st_size<2_000_000:
    raise SystemExit('Source cut was not produced or is unexpectedly small.')

out=WORK/'ep1.mp4'
run([
    'ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(raw),
    '-map','0:v:0','-map','0:a:0',
    '-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(out)
],timeout=2400)
actual=duration(out)
if not (575 <= actual <= 585):
    raise SystemExit(f'Part 1 source cut duration invalid: {actual:.3f}s')

item={
    'episode':1,
    'sourceUrl':SOURCE_URL,
    'shortDramaUrl':state.get('spotifyEpisodeUrl'),
    'videoId':source_id,
    'sourceHint':'spotify-queue-exact-title-public-copy',
    'sourceProvider':'facebook-public-copy',
    'sourceChannel':'babyjamie1',
    'file':str(out),
    'duration':actual,
}
(WORK/'episodes.json').write_text(json.dumps([item],indent=2)+'\n')
continuation={
    'sourceProvider':item['sourceProvider'],
    'sourceVideoId':source_id,
    'sourceUrl':SOURCE_URL,
    'sourceTitle':source_title,
    'sourceThumbnailUrl':thumb or None,
    'part':1,
    'storyTotalParts':story_total_parts,
    'startSeconds':0.0,
    'endSeconds':end,
    'fullDurationSeconds':full_duration,
    'storyComplete':False,
    'nextEpisode':2,
}
(WORK/'continuation.json').write_text(json.dumps(continuation,indent=2)+'\n')
print(json.dumps(continuation,indent=2))
