#!/usr/bin/env python3
import json, re, subprocess, urllib.parse
from difflib import SequenceMatcher
from pathlib import Path
from yt_dlp import YoutubeDL

BASE=Path('rubyclips')
STATE=BASE/'muffin_state.json'
OUT=BASE/'spotify_dailymotion_probe.json'
SAMPLE=BASE/'spotify_dailymotion_probe.mp4'

def norm(s):
    s=re.sub(r'[^a-z0-9]+',' ',str(s or '').lower())
    return re.sub(r'\s+',' ',s).strip()

def score_title(wanted,candidate):
    a,b=norm(wanted),norm(candidate)
    ratio=SequenceMatcher(None,a,b).ratio()
    aw={x for x in a.split() if len(x)>2}
    bw={x for x in b.split() if len(x)>2}
    overlap=(len(aw&bw)/max(1,len(aw))) if aw else 0.0
    containment=1.0 if a and (a in b or b in a) else 0.0
    return 0.55*ratio+0.35*overlap+0.10*containment

state=json.loads(STATE.read_text())
if str(state.get('sourceProvider') or '').lower()!='spotify-show':
    raise SystemExit('Spotify source is not active.')
title=str(state.get('currentSeriesTitle') or '').strip()
episode_id=str(state.get('currentSeriesId') or '').strip()
creator=str(state.get('spotifyCreator') or state.get('sourceChannel') or '').strip()
if not title or not episode_id:
    raise SystemExit('Spotify state is missing current episode identity.')

queries=[title]
if creator:
    queries.append(f'{title} {creator}')

seen={}
for q in queries:
    url='https://www.dailymotion.com/search/'+urllib.parse.quote_plus(q)+'/videos'
    opts={
        'quiet':True,'no_warnings':True,'extract_flat':True,'skip_download':True,
        'playlistend':20,'socket_timeout':30,'retries':2,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info=ydl.extract_info(url,download=False)
    except Exception as exc:
        print(f'Search failed for {q!r}: {exc}',flush=True)
        continue
    for e in (info or {}).get('entries') or []:
        vid=str(e.get('id') or '').strip()
        et=str(e.get('title') or '').strip()
        if not vid or not et:
            continue
        sc=score_title(title,et)
        prev=seen.get(vid)
        item={'id':vid,'title':et,'url':f'https://www.dailymotion.com/video/{vid}','score':round(sc,4),'query':q}
        if prev is None or sc>prev['score']:
            seen[vid]=item

ranked=sorted(seen.values(),key=lambda x:x['score'],reverse=True)
print('Spotify title:',title,flush=True)
for item in ranked[:10]:
    print(f"CANDIDATE score={item['score']:.4f} id={item['id']} title={item['title']}",flush=True)

if not ranked or ranked[0]['score']<0.62:
    result={'ok':False,'spotifyEpisodeId':episode_id,'spotifyTitle':title,'creator':creator,'candidates':ranked[:10],
            'error':'No sufficiently close Dailymotion title match.'}
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    raise SystemExit(result['error'])

chosen=ranked[0]
SAMPLE.unlink(missing_ok=True)
subprocess.run([
    'yt-dlp','--no-playlist','--no-progress','--socket-timeout','30','--retries','3',
    '--download-sections','*0-20','--force-keyframes-at-cuts',
    '-f','best[height<=720]/best','--merge-output-format','mp4',
    '-o',str(SAMPLE),chosen['url']
],check=True,timeout=300)

if not SAMPLE.exists() or SAMPLE.stat().st_size<100000:
    raise SystemExit('Matched Dailymotion source did not produce a usable sample.')
duration=float(subprocess.check_output([
    'ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(SAMPLE)
],text=True).strip())
if duration<5 or duration>30:
    raise SystemExit(f'Probe sample duration is invalid: {duration:.3f}s')

result={
    'ok':True,'spotifyEpisodeId':episode_id,'spotifyTitle':title,'creator':creator,
    'sourceProvider':'dailymotion','sourceVideoId':chosen['id'],'sourceUrl':chosen['url'],
    'sourceTitle':chosen['title'],'titleMatchScore':chosen['score'],
    'sampleDurationSeconds':round(duration,3),'sampleBytes':SAMPLE.stat().st_size,
    'candidates':ranked[:10],
}
OUT.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
