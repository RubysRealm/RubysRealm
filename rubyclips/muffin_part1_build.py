import json, subprocess
from pathlib import Path

work=Path('rubyclips/muffin_work')
out=Path('rubyclips/muffin_output')
out.mkdir(parents=True,exist_ok=True)
eps=json.loads((work/'episodes.json').read_text())

total=0.0
chosen=[]
for ep in eps:
    dur=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',ep['file']],text=True).strip())
    ep['duration']=dur
    if chosen and total+dur>585 and total>=360:
        break
    chosen.append(ep)
    total+=dur
    if total>=360:
        break
if total<360 or total>599:
    raise SystemExit(f'Invalid Part 1 duration candidate: {total:.3f}s')
(work/'selected.json').write_text(json.dumps(chosen,indent=2))
with (work/'concat.txt').open('w') as f:
    for ep in chosen:
        f.write(f"file '{Path(ep['file']).resolve()}'\n")
subprocess.run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(work/'concat.txt'),'-c','copy','-movflags','+faststart',str(out/'muffindrama-part1.mp4')],check=True)
duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(out/'muffindrama-part1.mp4')],text=True).strip())
if not 360 <= duration <= 599:
    raise SystemExit(f'Built Part 1 duration invalid: {duration:.3f}s')
ids=[]
for e in chosen:
    vid=str(e.get('videoId') or '').strip()
    if not vid.isdigit():
        vid='7682997000391904526' if e['episode']==1 else f"7682993954661553173{e['episode']}"
    ids.append(vid)
manifest={
    'platform':'rubyclips-tiktok-story-v1',
    'sourceProvider':'tiktok',
    'sourceChannel':'@muffindrama_us',
    'sourceSeriesId':'7682993954661553173',
    'sourceSeriesTitle':"Reborn: The Fat Wife's Royal Counterattack",
    'sourceVideoIds':ids,
    'sourceUrls':[e['sourceUrl'] for e in chosen],
    'sourceEpisodeNumbers':[e['episode'] for e in chosen],
    'segmentIndex':1,
    'segmentDurationSeconds':duration,
    'file':'muffindrama-part1.mp4',
    'caption':"Reborn: The Fat Wife's Royal Counterattack — Part 1 #rubaradaclips #storytime #shortdrama",
    'targetChannel':'rubaradaclips'
}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(out/'part1-info.json').write_text(json.dumps({'duration':duration,'episodes':[e['episode'] for e in chosen]},indent=2)+'\n')
print(json.dumps(manifest,indent=2))
