#!/usr/bin/env python3
import json, re, subprocess, textwrap
from pathlib import Path

BASE = Path('rubyclips')
WORK = BASE / 'muffin_work'
OUT = BASE / 'muffin_output'
STATE = BASE / 'muffin_state.json'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
PACKING_TARGET_SECONDS = 590.0
HARD_MAX_SECONDS = 598.5
OUTPUT_FPS = 30
PIPELINE_REVISION = 'avsync-v3-idempotent'

OUT.mkdir(parents=True, exist_ok=True)
state = json.loads(STATE.read_text())
eps = json.loads((WORK / 'episodes.json').read_text())
next_ep = int(state['nextEpisode'])
part = int(state['nextPart'])
restart_generation = int(state.get('restartGeneration', 2))
series_id = str(state['currentSeriesId'])
series_title = str(state['currentSeriesTitle']).strip()
logical_post_key = f'rubyclips:{series_id}:r{restart_generation}:p{part}'

ordered = sorted((e for e in eps if int(e['episode']) >= next_ep), key=lambda e: int(e['episode']))
if not ordered or int(ordered[0]['episode']) != next_ep:
    raise SystemExit(f'Expected Episode {next_ep} first, resolver returned something else.')

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
    if chosen and total + dur > PACKING_TARGET_SECONDS:
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

wrapped = textwrap.wrap(series_title, width=34, break_long_words=False, break_on_hyphens=False)
title_text = '\n'.join(wrapped[:2]) if wrapped else series_title
(WORK / 'story-title.txt').write_text(title_text, encoding='utf-8')
(WORK / 'part-label.txt').write_text(f'Part {part}', encoding='utf-8')

def esc(p):
    return p.as_posix().replace(':','\\:').replace("'","\\'")

# Normalize every source episode independently before concatenation. This
# intentionally avoids concat-demuxer stream copying because mixed source
# timestamps/frame pacing can freeze video while audio continues.
inputs = []
filters = []
concat_inputs = []
for i, ep in enumerate(chosen):
    inputs += ['-i', ep['file']]
    filters.append(
        f'[{i}:v]fps={OUTPUT_FPS},settb=AVTB,setpts=PTS-STARTPTS,'
        'scale=1080:1920:force_original_aspect_ratio=decrease,'
        'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p'
        f'[v{i}]'
    )
    filters.append(
        f'[{i}:a]aresample=48000:async=1:first_pts=0,asetpts=PTS-STARTPTS[a{i}]'
    )
    concat_inputs.append(f'[v{i}][a{i}]')

filters.append(''.join(concat_inputs) + f'concat=n={len(chosen)}:v=1:a=1[vcat][acat]')
filters.append(
    f"[vcat]drawtext=fontfile={FONT}:textfile='{esc(WORK/'story-title.txt')}':"
    "fontcolor=white:fontsize=35:line_spacing=5:box=1:boxcolor=black@0.68:boxborderw=14:"
    "x=(w-text_w)/2:y=125,"
    f"drawtext=fontfile={FONT}:textfile='{esc(WORK/'part-label.txt')}':"
    "fontcolor=white:fontsize=31:box=1:boxcolor=black@0.68:boxborderw=11:"
    "x=(w-text_w)/2:y=245[vout]"
)

final = OUT / f'muffindrama-{series_id}-r{restart_generation}-part-{part:02d}.mp4'
subprocess.run([
    'ffmpeg','-y','-hide_banner','-loglevel','error',*inputs,
    '-filter_complex',';'.join(filters),
    '-map','[vout]','-map','[acat]',
    '-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-r',str(OUTPUT_FPS),
    '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart','-shortest',str(final)
], check=True, timeout=3000)

duration = float(subprocess.check_output([
    'ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(final)
], text=True).strip())
if duration > HARD_MAX_SECONDS:
    raise SystemExit(f'Built part exceeds TikTok limit: {duration:.3f}s')
if final.stat().st_size < 100000:
    raise SystemExit('Built MP4 is unexpectedly small.')

# Verify the encoded video stream itself lasts essentially as long as the
# container/audio. This catches the exact frozen-last-frame failure before post.
video_duration = float(subprocess.check_output([
    'ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=duration','-of','default=nw=1:nk=1',str(final)
], text=True).strip())
audio_duration = float(subprocess.check_output([
    'ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=duration','-of','default=nw=1:nk=1',str(final)
], text=True).strip())
if abs(video_duration - audio_duration) > 1.0 or abs(video_duration - duration) > 1.0:
    raise SystemExit(f'A/V duration mismatch: video={video_duration:.3f}s audio={audio_duration:.3f}s container={duration:.3f}s')

ids = [str(e['videoId']) for e in chosen]
if any(not x.isdigit() for x in ids):
    raise SystemExit('Resolver returned a non-numeric TikTok video ID.')
urls = [str(e['sourceUrl']) for e in chosen]
nums = [int(e['episode']) for e in chosen]
story_hashtag = '#' + re.sub(r'[^A-Za-z0-9]+', '', series_title)
if story_hashtag == '#':
    raise SystemExit('Could not build story hashtag from story title.')

manifest = {
    'platform': 'rubyclips-tiktok-story-v1',
    'pipelineRevision': PIPELINE_REVISION,
    'logicalPostKey': logical_post_key,
    'sourceProvider': 'tiktok',
    'sourceChannel': '@muffindrama_us',
    'sourceSeriesId': series_id,
    'sourceSeriesTitle': series_title,
    'restartGeneration': restart_generation,
    'sourceVideoIds': ids,
    'sourceUrls': urls,
    'sourceEpisodeNumbers': nums,
    'segmentIndex': part,
    'segmentDurationSeconds': round(duration, 3),
    'file': final.name,
    'storyHashtag': story_hashtag,
    'caption': f'{series_title} — Part {part} {story_hashtag} #rubaradaclips #storytime #shortdrama',
    'targetChannel': 'rubaradaclips',
    'titleBurnedIn': True,
    'partLabelBurnedIn': True,
    'overlayLayoutVersion': 'story-title-lowered-v2',
    'concatPolicy': 'normalized-filter-concat-v2',
    'packingPolicy': 'max-whole-episodes-under-590s'
}
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(OUT / 'part-info.json').write_text(json.dumps({
    'part': part,
    'duration': duration,
    'videoDuration': video_duration,
    'audioDuration': audio_duration,
    'episodes': nums,
    'nextEpisode': nums[-1] + 1,
    'storyComplete': nums[-1] >= last_episode,
    'restartGeneration': restart_generation,
    'storyHashtag': story_hashtag,
    'pipelineRevision': PIPELINE_REVISION,
    'logicalPostKey': logical_post_key
}, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
