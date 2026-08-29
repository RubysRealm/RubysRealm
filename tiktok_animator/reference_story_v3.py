import os
import reference_story_v2 as engine
import reference_quality_patch as patch
from story_generator import generate_story

engine.fetch_photo=patch.fetch_photo
engine.select_visuals=patch.select_visuals
engine.verify=patch.verify


def choose_story(seed):
    supplied=os.getenv('STORY_TEXT','').strip()
    if supplied:
        return {
            'title':os.getenv('STORY_TITLE',"Ruby's Realm Story").strip() or "Ruby's Realm Story",
            'part':os.getenv('STORY_PART','Part 1').strip() or 'Part 1',
            'story':supplied,
            'source':'supplied'
        }

    ai=engine.gateway_story(seed)
    if ai:
        ai['source']='ai-gateway-original'
        return ai

    generated=generate_story(seed)
    return {
        'title':generated['title'],
        'part':generated.get('part','Part 1'),
        'story':generated['story'],
        'story_id':generated['story_id'],
        'source':'procedural-original-v3'
    }

engine.choose_story=choose_story

if __name__=='__main__':
    engine.main()
