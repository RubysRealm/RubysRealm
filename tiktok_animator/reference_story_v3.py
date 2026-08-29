import os
import reference_story_v2 as engine
import reference_quality_patch as patch
import reference_semantic_v5 as semantic
import reference_scheduler_v6 as scheduler
import reference_target_v7 as target
import reference_generated_v8 as generated
from story_generator import generate_story

generated.bind(target)

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

# Generate reference-style story illustrations first; semantic photography remains only a fallback.
def prepare_visuals(visuals,seed):
    return target.prepare_visuals(visuals,seed,semantic.fetch_photo)

engine.prepare_visuals=prepare_visuals


def choose_story(seed):
    supplied=os.getenv('STORY_TEXT','').strip()
    if supplied:
        info={'title':os.getenv('STORY_TITLE',"Ruby's Realm Story").strip() or "Ruby's Realm Story",'part':os.getenv('STORY_PART','Part 1').strip() or 'Part 1','story':supplied,'source':'supplied'}
        patch.set_context(info['title'])
        return info
    ai=engine.gateway_story(seed)
    if ai:
        ai['source']='ai-gateway-original'
        patch.set_context(ai['title'])
        return ai
    generated_story=generate_story(seed)
    info={'title':generated_story['title'],'part':generated_story.get('part','Part 1'),'story':generated_story['story'],'story_id':generated_story['story_id'],'source':'procedural-original-v3'}
    patch.set_context(info['title'])
    return info

engine.choose_story=choose_story

if __name__=='__main__':
    engine.main()
