import json, os, sys, time
from pathlib import Path
import urllib.request

ROOT='https://open.tiktokapis.com'
OUT=Path('tiktok_animator/output')
RENDERER='reference-narration-story-v2'
GATE='reference-photographic-story-v2'

def post(path,token,body):
    req=urllib.request.Request(ROOT+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json; charset=UTF-8'},method='POST')
    with urllib.request.urlopen(req,timeout=60) as r: payload=json.loads(r.read().decode())
    err=payload.get('error') or {}
    if err.get('code') not in (None,'','ok'): raise RuntimeError(str(err))
    return payload.get('data') or {}

def approved_output():
    manifests=sorted(OUT.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    if not manifests: raise RuntimeError('No quality manifest to authorize publishing')
    manifest=json.loads(manifests[0].read_text())
    if not manifest.get('qualityPassed'): raise RuntimeError('Quality gate did not pass')
    if manifest.get('renderer')!=RENDERER or manifest.get('qualityGate')!=GATE: raise RuntimeError('Wrong renderer or quality gate')
    checks=manifest.get('checks') or {}
    if not checks or not all(checks.values()): raise RuntimeError('One or more required quality checks failed')
    if float(manifest.get('photoSourceRatio') or 0)<0.65: raise RuntimeError('Insufficient legitimate photographic visual coverage')
    video=OUT/manifest.get('file','')
    if not video.exists(): raise RuntimeError('Approved video file is missing')
    dur=float(manifest.get('durationSeconds') or 0)
    if not 120<=dur<=540: raise RuntimeError('Approved video duration is outside 2-9 minutes')
    return video,manifest

def main():
    token=os.environ.get('TT_TOKEN','').strip()
    if not token: raise RuntimeError('TikTok authorization is not configured')
    video,manifest=approved_output()
    creator=post('/v2/post/publish/creator_info/query/',token,{})
    privacy='PUBLIC_TO_EVERYONE' if 'PUBLIC_TO_EVERYONE' in (creator.get('privacy_level_options') or []) else 'SELF_ONLY'
    title=str(manifest.get('title') or "Ruby's Realm Story")
    caption=f"{title} {manifest.get('part','Part 1')} #storytime #storytok #aistory #rubysrealm"
    size=video.stat().st_size
    init=post('/v2/post/publish/video/init/',token,{'post_info':{'title':caption,'privacy_level':privacy,'disable_duet':False,'disable_comment':False,'disable_stitch':False,'video_cover_timestamp_ms':1000},'source_info':{'source':'FILE_UPLOAD','video_size':size,'chunk_size':size,'total_chunk_count':1}})
    url=init['upload_url']; publish_id=init['publish_id']; data=video.read_bytes()
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'video/mp4','Content-Length':str(size),'Content-Range':f'bytes 0-{size-1}/{size}'},method='PUT')
    with urllib.request.urlopen(req,timeout=300) as r: r.read()
    for _ in range(45):
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

# Production trigger marker: 2026-08-29 10:20 ET
