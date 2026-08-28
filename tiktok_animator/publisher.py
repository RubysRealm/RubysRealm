import json, os, subprocess, sys, time
from pathlib import Path
import urllib.request, urllib.error

ROOT='https://open.tiktokapis.com'
OUT=Path('tiktok_animator/output')

def post(path, token, body):
    req=urllib.request.Request(ROOT+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json; charset=UTF-8'},method='POST')
    with urllib.request.urlopen(req,timeout=60) as r:
        payload=json.loads(r.read().decode())
    err=payload.get('error') or {}
    if err.get('code') not in (None,'','ok'):
        raise RuntimeError(str(err))
    return payload.get('data') or {}

def main():
    token=os.environ.get('TT_TOKEN','').strip()
    if not token:
        raise RuntimeError('TikTok authorization is not configured')
    videos=sorted(OUT.glob('*.mp4'),key=lambda p:p.stat().st_mtime,reverse=True)
    if not videos: raise RuntimeError('No video to publish')
    video=videos[0]
    creator=post('/v2/post/publish/creator_info/query/',token,{})
    privacy='PUBLIC_TO_EVERYONE' if 'PUBLIC_TO_EVERYONE' in (creator.get('privacy_level_options') or []) else 'SELF_ONLY'
    size=video.stat().st_size
    init=post('/v2/post/publish/video/init/',token,{'post_info':{'title':video.stem.replace('-',' ').title()+' #storytime #animatedstory','privacy_level':privacy,'disable_duet':False,'disable_comment':False,'disable_stitch':False,'video_cover_timestamp_ms':1000},'source_info':{'source':'FILE_UPLOAD','video_size':size,'chunk_size':size,'total_chunk_count':1}})
    url=init['upload_url']; publish_id=init['publish_id']
    data=video.read_bytes()
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'video/mp4','Content-Length':str(size),'Content-Range':f'bytes 0-{size-1}/{size}'},method='PUT')
    with urllib.request.urlopen(req,timeout=300) as r: r.read()
    for _ in range(30):
        status=post('/v2/post/publish/status/fetch/',token,{'publish_id':publish_id})
        state=(status.get('status') or status.get('publish_status') or '').upper()
        if state in ('PUBLISH_COMPLETE','SUCCESS','COMPLETED','POSTED'):
            print('published',publish_id); return
        if state in ('FAILED','PUBLISH_FAILED','ERROR'): raise RuntimeError(str(status))
        time.sleep(10)
    print('upload accepted',publish_id)

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(e,file=sys.stderr); sys.exit(1)
