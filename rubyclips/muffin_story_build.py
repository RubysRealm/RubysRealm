#!/usr/bin/env python3
import json, subprocess, textwrap
from pathlib import Path

BASE = Path('rubyclips')
WORK = BASE / 'muffin_work'
OUT = BASE / 'muffin_output'
STATE = BASE / 'muffin_state.json'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
PACKING_TARGET_SECONDS = 598.0
HARD_MAX_SECONDS = 599.0

OUT.mkdir(parents=True, exist_ok=True)
state = json.loads(STATE.read_text())
eps = json.loads((WORK / 'episodes.json').read_text())
next_ep = int(state['nextEpisode'])
part = int(state['nextPart'])
series_id = str(state['currentSeriesId'])
series_title = str(state['currentSeriesTitle']).strip()

ordered = sorted((e for e in eps if int(e['episode']) >= next_ep), key=lambda e: int(e['episode']))
if not ordered or int(ordered[0]['episode']) != next_ep:
    raise SystemExit(f'Expected Episode {next_ep} first, resolver returned something else.')

# Pack as many complete, consecutive source episodes as will fit under the
# automatic TikTok publishing ceiling. This intentionally favors longer parts
# (normally just under 10 minutes) over the old 6-minute minimum behavior.
chosen = []
total = 0.0
for ep in ordered:
    expected = next_ep + len(chosen)
    if int(ep['episode']) != expected:
        raise SystemExit(f'Episode sequence gap: expected {expected}, got {ep["episode"]}.')
    dur = float(subprocess.check_output([
        'ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',ep['file']
    ], text=True).strip())
    ep['duration'] = dur
    if dur > HARD_MAX_SECONDS:
        raise SystemExit(f'Episode {ep["episode"]} is too long to pack whole: {dur:.3f}s')
    if chosen and total + dur > HARD_MAX_SECONDS:
        break
    chosen.append(ep)
    total += dur
    if total >= PACKING_TARGET_SECONDS:
        break

last_episode = int(state['currentSeriesEpisodeCount'])
if not chosen:
    raise SystemExit('No episodes selected.')
if total > HARD_MAX_SECONDS:
    raise SystemExit(f'Part candidate too long: {total:.3f}s')

(WORK / 'selected.json').write_text(json.dumps(chosen, indent=2) + '\n')
with (WORK / 'concat.txt').open('w') as f:
    for ep in chosen:
        f.write(f"file '{Path(ep['file']).resolve()}'\n")

raw = WORK / f'part-{part:02d}-raw.mp4'
subprocess.run([
    'ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(WORK/'concat.txt'),
    '-c','copy','-movflags','+faststart',str(raw)
], check=True)

wrapped = textwrap.wrap(series_title, width=34, break_long_words=False, break_on_hyphens=False)
title_text = '\n'.join(wrapped[:2]) if wrapped else series_title
(WORK / 'story-title.txt').write_text(title_text, encoding='utf-8')
(WORK / 'part-label.txt').write_text(f'Part {part}', encoding='utf-8')

def esc(p):
    return p.as_posix().replace(':','\\:').replace("'","\\'")

final = OUT / f'muffindrama-{series_id}-part-{part:02d}.mp4'
vf = (
    'scale=1080:1920:force_original_aspect_ratio=decrease,'
    'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,'
    f"drawtext=fontfile={FONT}:textfile='{esc(WORK/'story-title.txt')}':"
    "fontcolor=white:fontsize=35:line_spacing=5:box=1:boxcolor=black@0.68:boxborderw=14:"
    "x=(w-text_w)/2:y=38,"
    f"drawtext=fontfile={FONT}:textfile='{esc(WORK/'part-label.txt')}':"
    "fontcolor=white:fontsize=31:box=1:boxcolor=black@0.68:boxborderw=11:"
    "x=(w-text_w)/2:y=155"
)
subprocess.run([
    'ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(raw),'-vf',vf,
    '-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(final)
], check=True, timeout=3000)

duration = float(subprocess.check_output([
    'ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(final)
], text=True).strip())
if duration > HARD_MAX_SECONDS:
    raise SystemExit(f'Built part exceeds TikTok limit: {duration:.3f}s')
if final.stat().st_size < 100000:
    raise SystemExit('Built MP4 is unexpectedly small.')

ids = [str(e['videoId']) for e in chosen]
if any(not x.isdigit() for x in ids):
    raise SystemExit('Resolver returned a non-numeric TikTok video ID.')
urls = [str(e['sourceUrl']) for e in chosen]
nums = [int(e['episode']) for e in chosen]
manifest = {
    'platform': 'rubyclips-tiktok-story-v1',
    'sourceProvider': 'tiktok',
    'sourceChannel': '@muffindrama_us',
    'sourceSeriesId': series_id,
    'sourceSeriesTitle': series_title,
    'sourceVideoIds': ids,
    'sourceUrls': urls,
    'sourceEpisodeNumbers': nums,
    'segmentIndex': part,
    'segmentDurationSeconds': round(duration, 3),
    'file': final.name,
    'caption': f'{series_title} — Part {part} #rubaradaclips #storytime #shortdrama',
    'targetChannel': 'rubaradaclips',
    'titleBurnedIn': True,
    'partLabelBurnedIn': True,
    'overlayLayoutVersion': 'story-title-top-v1',
    'packingPolicy': 'max-whole-episodes-under-599s'
}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(OUT / 'part-info.json').write_text(json.dumps({
    'part': part,
    'duration': duration,
    'episodes': nums,
    'nextEpisode': nums[-1] + 1,
    'storyComplete': nums[-1] >= last_episode
}, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
