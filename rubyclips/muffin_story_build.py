#!/usr/bin/env python3
import json, re, shutil, subprocess, textwrap
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
# Keep the complete source frame visibly inside the 1080x1920 TikTok canvas.
# The previous 1048x1862 treatment was only ~3% inset and still looked zoomed.
# This 900x1600 presentation is ~16.7% inset in each dimension and is backed by
# a blurred full-canvas copy so the result stays full-screen without black bars.
CONTENT_WIDTH = 900
CONTENT_HEIGHT = 1600
SOURCE_FRAME_INSET_PERCENT = 16.7
COVER_SECONDS = 1.25
THUMBNAIL_OFFSET_MS = 1000


def supports_drawtext(binary):
    try:
        result = subprocess.run(
            [binary, '-hide_banner', '-filters'],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0 and re.search(r'\bdrawtext\b', result.stdout) is not None
    except Exception:
        return False


def resolve_ffmpeg_tools():
    ffmpeg = shutil.which('ffmpeg') or 'ffmpeg'
    ffprobe = shutil.which('ffprobe') or 'ffprobe'
    if supports_drawtext(ffmpeg):
        return ffmpeg, ffprobe

    brew = shutil.which('brew')
    if not brew:
        raise SystemExit('FFmpeg is missing drawtext and Homebrew is unavailable for the ffmpeg-full fallback.')
    print('Current FFmpeg lacks drawtext; installing/selecting Homebrew ffmpeg-full...')
    subprocess.run([brew, 'install', 'ffmpeg-full'], check=True, timeout=2400)
    prefix = subprocess.check_output([brew, '--prefix', 'ffmpeg-full'], text=True).strip()
    full_ffmpeg = str(Path(prefix) / 'bin' / 'ffmpeg')
    full_ffprobe = str(Path(prefix) / 'bin' / 'ffprobe')
    if not supports_drawtext(full_ffmpeg):
        raise SystemExit(f'ffmpeg-full installed but drawtext is still unavailable: {full_ffmpeg}')
    return full_ffmpeg, full_ffprobe


FFMPEG, FFPROBE = resolve_ffmpeg_tools()
print('Using FFmpeg:', FFMPEG)

OUT.mkdir(parents=True, exist_ok=True)
state = json.loads(STATE.read_text())
continuation_path = WORK / 'continuation.json'
continuation = json.loads(continuation_path.read_text()) if continuation_path.exists() else {}
eps = json.loads((WORK / 'episodes.json').read_text())
next_ep = int(state['nextEpisode'])
part = int(state['nextPart'])
story_total_parts = int(continuation.get('storyTotalParts') or state.get('storyTotalParts') or 0)
restart_generation = int(state.get('restartGeneration', 2))
series_id = str(state['currentSeriesId'])
series_title = str(state['currentSeriesTitle']).strip()
logical_post_key = f'rubyclips:{series_id}:r{restart_generation}:p{part}'
part_label = f'Part {part} of {story_total_parts}' if story_total_parts >= part else f'Part {part}'

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
        FFPROBE,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',ep['file']
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
(WORK / 'part-label.txt').write_text(part_label, encoding='utf-8')


def esc(p):
    return p.as_posix().replace(':','\\:').replace("'","\\'")


cover_candidates = sorted(p for p in WORK.glob('story-cover.*') if p.is_file())
cover_intro = None
if cover_candidates:
    cover_source = cover_candidates[0]
    cover_intro = WORK / 'story-cover-intro.mp4'
    cover_filter = (
        '[0:v]split=2[coverbgsrc][coverfgsrc];'
        '[coverbgsrc]scale=1080:1920:force_original_aspect_ratio=increase,'
        'crop=1080:1920,gblur=sigma=24[coverbg];'
        f'[coverfgsrc]scale={CONTENT_WIDTH}:{CONTENT_HEIGHT}:force_original_aspect_ratio=decrease[coverfg];'
        '[coverbg][coverfg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[vcover]'
    )
    subprocess.run([
        FFMPEG,'-y','-hide_banner','-loglevel','error',
        '-loop','1','-framerate',str(OUTPUT_FPS),'-i',str(cover_source),
        '-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000',
        '-filter_complex',cover_filter,
        '-map','[vcover]','-map','1:a:0','-t',str(COVER_SECONDS),
        '-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-r',str(OUTPUT_FPS),
        '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart','-shortest',str(cover_intro)
    ], check=True, timeout=300)
    if cover_intro.stat().st_size < 50000:
        raise SystemExit('Built story cover intro is unexpectedly small.')
    print('Embedded source story artwork for TikTok preview:', cover_source)

# Normalize each source independently. For story footage, create a blurred
# edge-to-edge background from the same frame, then overlay a substantially
# smaller untouched foreground copy. The foreground uses `decrease`, never
# `increase` or crop, so the source frame is preserved in full.
render_clips = []
if cover_intro:
    render_clips.append({'file': str(cover_intro), 'cover': True})
render_clips.extend({'file': ep['file'], 'cover': False} for ep in chosen)

inputs = []
filters = []
concat_inputs = []
for i, clip in enumerate(render_clips):
    inputs += ['-i', clip['file']]
    if clip['cover']:
        filters.append(
            f'[{i}:v]fps={OUTPUT_FPS},settb=AVTB,setpts=PTS-STARTPTS,'
            'scale=1080:1920:force_original_aspect_ratio=decrease,'
            'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p[v%d]' % i
        )
    else:
        filters.append(
            f'[{i}:v]fps={OUTPUT_FPS},settb=AVTB,setpts=PTS-STARTPTS,split=2[bgsrc{i}][fgsrc{i}]'
        )
        filters.append(
            f'[bgsrc{i}]scale=1080:1920:force_original_aspect_ratio=increase,'
            f'crop=1080:1920,gblur=sigma=30[bg{i}]'
        )
        filters.append(
            f'[fgsrc{i}]scale={CONTENT_WIDTH}:{CONTENT_HEIGHT}:force_original_aspect_ratio=decrease[fg{i}]'
        )
        filters.append(
            f'[bg{i}][fg{i}]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v{i}]'
        )
    filters.append(
        f'[{i}:a]aresample=48000:async=1:first_pts=0,asetpts=PTS-STARTPTS[a{i}]'
    )
    concat_inputs.append(f'[v{i}][a{i}]')

filters.append(''.join(concat_inputs) + f'concat=n={len(render_clips)}:v=1:a=1[vcat][acat]')
overlay_enable = f":enable='gte(t,{COVER_SECONDS})'" if cover_intro else ''
filters.append(
    f"[vcat]drawtext=fontfile={FONT}:textfile='{esc(WORK/'story-title.txt')}':"
    "fontcolor=white:fontsize=35:line_spacing=5:box=1:boxcolor=black@0.68:boxborderw=14:"
    f"x=(w-text_w)/2:y=195{overlay_enable},"
    f"drawtext=fontfile={FONT}:textfile='{esc(WORK/'part-label.txt')}':"
    "fontcolor=white:fontsize=31:box=1:boxcolor=black@0.68:boxborderw=11:"
    f"x=(w-text_w)/2:y=315{overlay_enable}[vout]"
)

final = OUT / f'muffindrama-{series_id}-r{restart_generation}-part-{part:02d}.mp4'
subprocess.run([
    FFMPEG,'-y','-hide_banner','-loglevel','error',*inputs,
    '-filter_complex',';'.join(filters),
    '-map','[vout]','-map','[acat]',
    '-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-r',str(OUTPUT_FPS),
    '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart','-shortest',str(final)
], check=True, timeout=3000)

duration = float(subprocess.check_output([
    FFPROBE,'-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(final)
], text=True).strip())
if duration > HARD_MAX_SECONDS:
    raise SystemExit(f'Built part exceeds TikTok limit: {duration:.3f}s')
if final.stat().st_size < 100000:
    raise SystemExit('Built MP4 is unexpectedly small.')

video_duration = float(subprocess.check_output([
    FFPROBE,'-v','error','-select_streams','v:0','-show_entries','stream=duration','-of','default=nw=1:nk=1',str(final)
], text=True).strip())
audio_duration = float(subprocess.check_output([
    FFPROBE,'-v','error','-select_streams','a:0','-show_entries','stream=duration','-of','default=nw=1:nk=1',str(final)
], text=True).strip())
if abs(video_duration - audio_duration) > 1.0 or abs(video_duration - duration) > 1.0:
    raise SystemExit(f'A/V duration mismatch: video={video_duration:.3f}s audio={audio_duration:.3f}s container={duration:.3f}s')

source_provider = str(chosen[0].get('sourceProvider') or 'tiktok').lower()
source_channel = str(chosen[0].get('sourceChannel') or '@muffindrama_us')
ids = [str(e['videoId']) for e in chosen]
if source_provider == 'tiktok' and any(not x.isdigit() for x in ids):
    raise SystemExit('TikTok resolver returned a non-numeric video ID.')
urls = [str(e['sourceUrl']) for e in chosen]
nums = [int(e['episode']) for e in chosen]
story_hashtag = '#' + re.sub(r'[^A-Za-z0-9]+', '', series_title)
if story_hashtag == '#':
    raise SystemExit('Could not build story hashtag from story title.')

story_complete = bool(continuation.get('storyComplete')) if continuation else nums[-1] >= last_episode
next_episode_after_part = int(continuation.get('nextEpisode') or (nums[-1] + 1))
manifest = {
    'platform': 'rubyclips-tiktok-story-v1',
    'pipelineRevision': PIPELINE_REVISION,
    'logicalPostKey': logical_post_key,
    'sourceProvider': source_provider,
    'sourceChannel': source_channel,
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
    'caption': f'{series_title} — {part_label} {story_hashtag} #rubaradaclips #storytime #shortdrama',
    'targetChannel': 'rubaradaclips',
    'titleBurnedIn': True,
    'partLabelBurnedIn': True,
    'overlayLayoutVersion': 'story-title-lowered-v4-wide-frame',
    'concatPolicy': 'normalized-filter-concat-v2',
    'packingPolicy': 'max-whole-episodes-under-590s',
    'sourceFrameInsetPercent': SOURCE_FRAME_INSET_PERCENT,
    'sourceFrameMode': 'full-frame-blurred-background-v1',
    'coverArtEmbedded': bool(cover_intro),
    'coverDurationSeconds': COVER_SECONDS if cover_intro else 0,
    'thumbnailOffsetMs': THUMBNAIL_OFFSET_MS if cover_intro else 1000
}
if continuation.get('sourceThumbnailUrl'):
    manifest['sourceThumbnailUrl'] = continuation['sourceThumbnailUrl']
if story_total_parts >= part:
    manifest['segmentTotal'] = story_total_parts
(OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(OUT / 'part-info.json').write_text(json.dumps({
    'part': part,
    'totalParts': story_total_parts or None,
    'duration': duration,
    'videoDuration': video_duration,
    'audioDuration': audio_duration,
    'episodes': nums,
    'nextEpisode': next_episode_after_part,
    'storyComplete': story_complete,
    'restartGeneration': restart_generation,
    'storyHashtag': story_hashtag,
    'pipelineRevision': PIPELINE_REVISION,
    'logicalPostKey': logical_post_key,
    'sourceFrameInsetPercent': SOURCE_FRAME_INSET_PERCENT,
    'sourceFrameMode': 'full-frame-blurred-background-v1',
    'coverArtEmbedded': bool(cover_intro),
    'thumbnailOffsetMs': THUMBNAIL_OFFSET_MS if cover_intro else 1000
}, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
