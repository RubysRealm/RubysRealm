#!/usr/bin/env python3
import json,re,subprocess
from pathlib import Path
from difflib import SequenceMatcher

TITLE='His Mom Made Him Kneel On Broken Glass'
TIKTOK='https://www.tiktok.com/@hisytstory/video/7614976629017742606'
OUT=Path('rubyclips/hisstory_transport_probe')
OUT.mkdir(parents=True,exist_ok=True)

def norm(s):
    return re.sub(r'[^a-z0-9]+',' ',str(s or '').lower()).strip()

def sim(a,b):
    return SequenceMatcher(None,norm(a),norm(b)).ratio()

def run(cmd,timeout=300):
    return subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)

results={}

# YouTube search: prefer exact official source if available.
yt=run([
    'yt-dlp','--skip-download','--dump-json','--no-warnings',
    '--socket-timeout','25','--retries','3',
    '--js-runtimes','node','--remote-components','ejs:github',
    f'ytsearch10:{TITLE} His Story'
],timeout=360)
rows=[]
for line in yt.stdout.splitlines():
    line=line.strip()
    if line.startswith('{'):
        try: rows.append(json.loads(line))
        except: pass
cand=[]
for r in rows:
    title=str(r.get('title') or '')
    uploader=' '.join(str(r.get(k) or '') for k in ('uploader','channel','uploader_id','channel_id'))
    score=sim(TITLE,title)
    official=('his story' in norm(uploader) or 'hisytstory' in norm(uploader))
    url=str(r.get('webpage_url') or r.get('url') or '')
    vid=str(r.get('id') or '')
    if vid and (not url.startswith('http') or 'youtube.com' not in url):
        url=f'https://www.youtube.com/watch?v={vid}'
    cand.append({'title':title,'uploader':uploader,'score':round(score,4),'official':official,'url':url,'id':vid,'duration':r.get('duration')})
cand.sort(key=lambda x:(x['official'],x['score'],float(x['duration'] or 0)),reverse=True)
results['youtubeCandidates']=cand[:10]

# TikTok known exact official post.
ttmeta=run(['yt-dlp','--skip-download','--dump-single-json','--no-warnings','--socket-timeout','30','--retries','3',TIKTOK],timeout=240)
tt_lines=[x.strip() for x in ttmeta.stdout.splitlines() if x.strip().startswith('{')]
if not tt_lines:
    results['tiktokError']=ttmeta.stdout[-1800:]
else:
    m=json.loads(tt_lines[-1])
    results['tiktokMeta']={
        'id':str(m.get('id') or ''),
        'title':str(m.get('title') or ''),
        'uploader':str(m.get('uploader') or ''),
        'duration':float(m.get('duration') or 0),
        'width':m.get('width'),'height':m.get('height')
    }
    sample=OUT/'tiktok-sample.mp4'
    dl=run([
        'yt-dlp','--no-playlist','--no-progress','--socket-timeout','30','--retries','4',
        '--download-sections','*0-30',
        '-f','bestvideo*+bestaudio/best','--merge-output-format','mp4',
        '-o',str(sample),TIKTOK
    ],timeout=600)
    results['tiktokDownloadLog']=dl.stdout[-1500:]
    if sample.exists():
        probe=json.loads(subprocess.check_output([
            'ffprobe','-v','error','-show_streams','-show_format','-of','json',str(sample)
        ],text=True))
        results['tiktokSample']={
            'bytes':sample.stat().st_size,
            'duration':float(probe['format']['duration']),
            'videoStreams':[{k:s.get(k) for k in ('codec_name','width','height','duration')} for s in probe['streams'] if s.get('codec_type')=='video'],
            'audioStreams':[{k:s.get(k) for k in ('codec_name','sample_rate','channels','duration')} for s in probe['streams'] if s.get('codec_type')=='audio']
        }
        subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss','8','-i',str(sample),'-frames:v','1',str(OUT/'tiktok-frame.jpg')],check=True)

(OUT/'result.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
