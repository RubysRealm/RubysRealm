import os
import reference_story_v2 as engine
import reference_quality_patch as patch
import reference_semantic_v5 as semantic
import reference_scheduler_v6 as scheduler
from story_generator import generate_story

engine.STYLE['visual_min_gap']=11.5
engine.STYLE['visual_max_gap']=18.3
engine.STYLE['visual_hold']=[5.4,6.8]
engine.STYLE['visual_coverage']=[0.30,0.55]
_original_context=patch.set_context

def set_context(title):
    _original_context(title)
    semantic.set_context(title)

patch.set_context=set_context
patch.contextual_visual_query=semantic.semantic_query
engine.fetch_photo=semantic.fetch_photo
engine.select_visuals=lambda beats,duration: scheduler.select_visuals(semantic,beats,duration)
_base_verify=patch.verify
engine.verify=lambda video,cues,visuals,narration,source_count: semantic.verify(_base_verify,video,cues,visuals,narration,source_count)
engine.visual_query=semantic.semantic_query


def choose_story(seed):
    supplied=os.getenv('STORY_TEXT','').strip()
    if supplied:
        info={'title':os.getenv('STORY_TITLE',"Ruby's Realm Story").strip() or "Ruby's Realm Story",'part':os.getenv('STORY_PART','Part 1').strip() or 'Part 1','story':supplied,'source':'supplied'}
        patch.set_context(info['title'])
        return info
    ai=engine.gateway_story(seed)
    if ai:
        ai['source']='ai-gateway-original'; patch.set_context(ai['title']); return ai
    generated=generate_story(seed)
    info={'title':generated['title'],'part':generated.get('part','Part 1'),'story':generated['story'],'story_id':generated['story_id'],'source':'procedural-original-v3'}
    patch.set_context(info['title'])
    return info

engine.choose_story=choose_story

if __name__=='__main__':
    engine.main()
