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
import reference_style_v9 as style_v9
from story_generator import generate_story

generated.bind(target)
style_v9.bind(target)

LAST_STORY_FINGERPRINT=None

# Bind the active renderer to the user's second reference example.
engine.compose_frame=target.compose_frame
engine.caption_cues=target.caption_cues
engine.write_ass=target.write_ass
engine.narrate=target.narrate
engine.fallback_tts=target.no_approximate_tts
engine.render=target.render
engine.select_visuals=lambda beats,duration: target.select_visuals(scheduler,semantic,beats,duration)
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
    return target.prepare_visuals(visuals,seed,lambda *_args,**_kwargs: {'source_type':'none','error':'realistic-photo fallback disabled'})

engine.prepare_visuals=prepare_visuals


def _story_fingerprint(story):
    normalized=re.sub(r'\s+',' ',str(story or '').strip().lower())
    return 'sha256:'+hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def choose_story(seed):
    global LAST_STORY_FINGERPRINT
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
