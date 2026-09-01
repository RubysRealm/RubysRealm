import hashlib
import json
import os
import re
from pathlib import Path

import reference_story_v2 as engine
import reference_quality_patch as patch
import reference_semantic_v5 as semantic
import reference_scheduler_v6 as scheduler
import reference_target_v7 as target
import reference_generated_v8 as generated
from story_generator import generate_story

generated.bind(target)

LAST_STORY_FINGERPRINT=None
EXTERNAL_PACK_PATH=Path('tiktok_animator/external_visual_pack.json')


def _external_pack():
    if not EXTERNAL_PACK_PATH.exists():
        return None
    data=json.loads(EXTERNAL_PACK_PATH.read_text())
    if not data.get('story') or not data.get('visuals'):
        raise RuntimeError('External visual pack is incomplete')
    return data


def _select_visuals(beats,duration):
    pack=_external_pack()
    if not pack:
        return target.select_visuals(scheduler,semantic,beats,duration)
    out=[]
    for item in pack['visuals']:
        st=float(item['start'])
        en=float(item.get('end',st+10.0))
        out.append({'start':st,'end':en,'duration':max(0.1,en-st),'query':item['beat_text'],'score':10.0,'beat_text':item['beat_text'],'external_url':item['url'],'scene_id':item.get('scene_id',len(out)+1),'continuity':item.get('continuity',{})})
    return out


# Bind the active renderer to the user's second reference example.
engine.compose_frame=target.compose_frame
engine.caption_cues=target.caption_cues
engine.write_ass=target.write_ass
engine.narrate=target.narrate
engine.fallback_tts=target.no_approximate_tts
engine.render=target.render
engine.select_visuals=lambda beats,duration: _select_visuals(beats,duration)
engine.verify=target.verify
engine.visual_query=semantic.semantic_query

_original_context=patch.set_context

def set_context(title):
    _original_context(title)
    semantic.set_context(title)
    target.set_story_context(title)

patch.set_context=set_context

# Production visuals must be generated cartoon illustrations only. No realistic-photo fallback.
def prepare_visuals(visuals,seed):
    pack=_external_pack()
    if pack:
        valid=[]
        seen_urls=set()
        for i,v in enumerate(visuals):
            url=str(v.get('external_url') or '').strip()
            if not url:
                raise RuntimeError(f'External visual URL missing at scene {i+1}')
            if url in seen_urls:
                raise RuntimeError(f'Reused external visual detected at scene {i+1}; every narration beat requires unique finished artwork')
            seen_urls.add(url)
            dest=Path(target.base.__file__).parent/'tmp'/f'external_visual_{i:02d}.jpg'
            dest.parent.mkdir(parents=True,exist_ok=True)
            target.base.download(url,dest,timeout=120)
            v['photo']=dest
            v['source']={'source_type':'ai-generated-illustration','model':'purpose-generated-external','via':'direct-finished-beat-art','query':v.get('beat_text','')}
            valid.append(v)
        visuals[:]=valid
        target.base.STYLE['generated_illustration_ratio']=1.0
        target.base.STYLE['visual_source_policy']='generated-cartoon-only'
        target.base.STYLE['photographic_fallback']='disabled'
        return len(visuals)
    return target.prepare_visuals(visuals,seed,lambda *_args,**_kwargs: {'source_type':'none','error':'realistic-photo fallback disabled'})

engine.prepare_visuals=prepare_visuals


def _story_fingerprint(story):
    normalized=re.sub(r'\s+',' ',str(story or '').strip().lower())
    return 'sha256:'+hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def choose_story(seed):
    global LAST_STORY_FINGERPRINT
    pack=_external_pack()
    if pack:
        info={'title':pack.get('title') or "Ruby's Realm Story",'part':pack.get('part') or 'Part 1','story':pack['story'],'source':'supplied'}
        LAST_STORY_FINGERPRINT=_story_fingerprint(info['story'])
        patch.set_context(info['title'])
        return info
    supplied=os.getenv('STORY_TEXT','').strip()
    if supplied:
        info={'title':os.getenv('STORY_TITLE',"Ruby's Realm Story").strip() or "Ruby's Realm Story",'part':os.getenv('STORY_PART','Part 1').strip() or 'Part 1','story':supplied,'source':'supplied'}
        LAST_STORY_FINGERPRINT=_story_fingerprint(info['story'])
        patch.set_context(info['title'])
        return info
    ai=engine.gateway_story(seed)
    if ai:
        ai['source']='ai-gateway-original'
        LAST_STORY_FINGERPRINT=_story_fingerprint(ai['story'])
        patch.set_context(ai['title'])
        return ai
    generated_story=generate_story(seed)
    info={'title':generated_story['title'],'part':generated_story.get('part','Part 1'),'story':generated_story['story'],'story_id':generated_story['story_id'],'source':'procedural-original-v3'}
    LAST_STORY_FINGERPRINT=_story_fingerprint(info['story'])
    patch.set_context(info['title'])
    return info

engine.choose_story=choose_story


def _file_sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return 'sha256:'+h.hexdigest()


def stamp_duplicate_fingerprints():
    out=Path('tiktok_animator/output')
    for manifest_path in out.glob('*.json'):
        data=json.loads(manifest_path.read_text())
        video=out/str(data.get('file',''))
        if not video.exists():
            raise RuntimeError('Cannot fingerprint rendered TikTok video')
        data['storyFingerprint']=LAST_STORY_FINGERPRINT
        data['videoFingerprint']=_file_sha256(video)
        data['duplicateGuard']='story-and-video-sha256-v1'
        manifest_path.write_text(json.dumps(data,indent=2))


if __name__=='__main__':
    engine.main()
    stamp_duplicate_fingerprints()
