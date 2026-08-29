import os
import reference_story_v2 as engine
import reference_quality_patch as patch
import reference_gap_fix as gapfix
from story_generator import generate_story

gapfix.bind(patch)
engine.fetch_photo=patch.fetch_photo
engine.select_visuals=lambda beats,duration: gapfix.select_visuals(patch,beats,duration)
engine.verify=patch.verify
engine.visual_query=patch.contextual_visual_query


def choose_story(seed):
    supplied=os.getenv('STORY_TEXT','').strip()
    if supplied:
        info={
            'title':os.getenv('STORY_TITLE',"Ruby's Realm Story").strip() or "Ruby's Realm Story",
            'part':os.getenv('STORY_PART','Part 1').strip() or 'Part 1',
            'story':supplied,
            'source':'supplied'
        }
        patch.set_context(info['title'])
        return info

    ai=engine.gateway_story(seed)
    if ai:
        ai['source']='ai-gateway-original'
        patch.set_context(ai['title'])
        return ai

    generated=generate_story(seed)
    info={
        'title':generated['title'],
        'part':generated.get('part','Part 1'),
        'story':generated['story'],
        'story_id':generated['story_id'],
        'source':'procedural-original-v3'
    }
    patch.set_context(info['title'])
    return info

engine.choose_story=choose_story

if __name__=='__main__':
    engine.main()
