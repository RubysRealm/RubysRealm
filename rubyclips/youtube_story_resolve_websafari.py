#!/usr/bin/env python3
import json, subprocess
from pathlib import Path

BASE=Path('rubyclips')
WORK=BASE/'muffin_work'
STATE=BASE/'muffin_state.json'
SOURCE_CHANNEL='@muffindrama-uvu'
CHUNK_SECONDS=595.0
HARD_MAX_SECONDS=598.5
YT_FORMAT='18/best[ext=mp4][vcodec^=avc1][acodec!=none][height<=720]/best[ext=mp4][acodec!=none][height<=720]/best[height<=720]'


def output(args):
    return subprocess.check_output(args,text=True).strip()


def duration(path):
    return float(output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]))

WORK.mkdir(parents=True,exist_ok=True)
state=json.loads(STATE.read_text())
if str(state.get('sourceProvider') or '').lower()!='youtube':
    raise SystemExit(2)
video_id=str(state['currentSeriesId'])
video_url=str(state.get('youtubeSourceUrl') or f'https://www.youtube.com/watch?v={video_id}')
part=int(state['nextPart'])
total_parts=int(state.get('storyTotalParts') or state['currentSeriesEpisodeCount'])
source_duration=float(state.get('sourceDurationSeconds') or 0)
start=(part-1)*CHUNK_SECONDS
remaining=source_duration-start
if remaining<=1:
    raise SystemExit(2)
clip_len=min(CHUNK_SECONDS,remaining)
end=start+clip_len
raw=WORK/'youtube-section-raw.mp4'
out=WORK/f'ep{part}.mp4'
for p in WORK.glob('youtube-section-raw.*'):
    if p.is_file(): p.unlink(missing_ok=True)
out.unlink(missing_ok=True)
section=f'*{start:.3f}-{end:.3f}'
cmd=[
    'yt-dlp','--no-playlist','--no-progress','--retries','20','--fragment-retries','20',
    '--retry-sleep','fragment:2','--js-runtimes','node','--remote-components','ejs:github',
    '--extractor-args','youtube:player_client=tv,web_safari',
    '--add-header','Referer:https://www.youtube.com/',
    '--add-header','Origin:https://www.youtube.com',
    '--download-sections',section,'-f',YT_FORMAT,'--merge-output-format','mp4','--remux-video','mp4',
    '-o',str(raw),video_url,
]
print('Trying current YouTube tv+web_safari client path with embed-compatible headers.',flush=True)
proc=subprocess.run(cmd)
if proc.returncode!=0 or not raw.exists() or raw.stat().st_size<500000:
    raise SystemExit(3)
subprocess.run([
    'ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(raw),'-t',f'{clip_len:.3f}',
    '-map','0:v:0','-map','0:a:0?','-c:v','libx264','-preset','ultrafast','-crf','22','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(out)
],check=True)
actual=duration(out)
if actual<5 or actual>HARD_MAX_SECONDS or out.stat().st_size<500000:
    raise SystemExit(4)
item={
    'episode':part,'sourceUrl':video_url,'shortDramaUrl':video_url,'videoId':video_id,
    'sourceHint':'muffindrama-youtube:tv-web_safari','sourceProvider':'youtube','sourceChannel':SOURCE_CHANNEL,
    'file':str(out),'duration':actual,
}
(WORK/'episodes.json').write_text(json.dumps([item],indent=2)+'\n')
story_complete=part>=total_parts
(WORK/'continuation.json').write_text(json.dumps({
    'sourceProvider':'youtube','sourceVideoId':video_id,'sourceUrl':video_url,'storyTotalParts':total_parts,
    'part':part,'startSeconds':round(start,3),'endSeconds':round(min(end,source_duration),3),
    'fullDurationSeconds':round(source_duration,3),'storyComplete':story_complete,
    'nextEpisode':total_parts+1 if story_complete else part+1,'sourceStrategy':'tv-web_safari',
},indent=2)+'\n')
print(json.dumps({'ok':True,'videoId':video_id,'part':part,'totalParts':total_parts,'duration':actual,'sourceStrategy':'tv-web_safari'},indent=2))
