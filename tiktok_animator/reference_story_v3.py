import reference_story_v2 as engine
import reference_quality_patch as patch

engine.fetch_photo=patch.fetch_photo
engine.select_visuals=patch.select_visuals
engine.verify=patch.verify

if __name__=='__main__':
    engine.main()
