#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

# This line is intentionally retained because the production workflow replaces
# it with the runner's verified bold font before execution.
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

BASE_COMMIT = '9855d693a016a15d7ba3d5e3c10ea571ded42b37'
BASE_PATH = 'rubyclips/muffin_story_build.py'
STATE_PATH = Path('rubyclips/muffin_state.json')

state = json.loads(STATE_PATH.read_text())
if int(state.get('nextPart', 1)) != 1:
    raise SystemExit('Rubaradaclips hold is active: Part 2+ is blocked until corrected Part 1 is approved.')

source = subprocess.check_output(
    ['git', 'show', f'{BASE_COMMIT}:{BASE_PATH}'],
    text=True,
)


def replace_once(old, new, label):
    global source
    count = source.count(old)
    if count != 1:
        raise SystemExit(f'Layout patch guard failed for {label}: expected 1 match, found {count}.')
    source = source.replace(old, new, 1)


replace_once(
    "FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'",
    f"FONT = {FONT!r}",
    'runner font',
)

replace_once(
'''    cover_filter = (
        '[0:v]split=2[coverbgsrc][coverfgsrc];'
        '[coverbgsrc]scale=1080:1920:force_original_aspect_ratio=increase,'
        'crop=1080:1920,gblur=sigma=24[coverbg];'
        f'[coverfgsrc]scale={CONTENT_WIDTH}:{CONTENT_HEIGHT}:force_original_aspect_ratio=decrease[coverfg];'
        '[coverbg][coverfg]overlay=(W-w)/2:(H-h)/2[coverbase];'
        f"[coverbase]drawtext=fontfile={FONT}:textfile='{esc(WORK/'story-title.txt')}':"
        "fontcolor=white:fontsize=58:line_spacing=8:box=1:boxcolor=black@0.72:boxborderw=20:"
        "x=(w-text_w)/2:y=520,"
        f"drawtext=fontfile={FONT}:textfile='{esc(WORK/'part-label.txt')}':"
        "fontcolor=white:fontsize=44:box=1:boxcolor=black@0.72:boxborderw=16:"
        "x=(w-text_w)/2:y=710,setsar=1,format=yuv420p[vcover]"
    )''',
'''    cover_filter = (
        f'[0:v]scale={CONTENT_WIDTH}:{CONTENT_HEIGHT}:force_original_aspect_ratio=decrease,'
        'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black[coverbase];'
        f"[coverbase]drawtext=fontfile={FONT}:textfile='{esc(WORK/'story-title.txt')}':"
        "fontcolor=white:fontsize=58:line_spacing=8:box=1:boxcolor=black@0.72:boxborderw=20:"
        "x=(w-text_w)/2:y=500,"
        f"drawtext=fontfile={FONT}:textfile='{esc(WORK/'part-label.txt')}':"
        "fontcolor=white:fontsize=44:box=1:boxcolor=black@0.72:boxborderw=16:"
        "x=(w-text_w)/2:y=650,setsar=1,format=yuv420p[vcover]"
    )''',
    'cover black pillarbox and tightened labels',
)

replace_once(
'''    else:
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
        )''',
'''    else:
        filters.append(
            f'[{i}:v]fps={OUTPUT_FPS},settb=AVTB,setpts=PTS-STARTPTS,'
            f'scale={CONTENT_WIDTH}:{CONTENT_HEIGHT}:force_original_aspect_ratio=decrease,'
            f'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p[v{i}]'
        )''',
    'live-video black pillarbox',
)

replace_once(
    'f"x=(w-text_w)/2:y=330{overlay_enable},"',
    'f"x=(w-text_w)/2:y=290{overlay_enable},"',
    'live title vertical position',
)
replace_once(
    'f"x=(w-text_w)/2:y=460{overlay_enable}[vout]"',
    'f"x=(w-text_w)/2:y=400{overlay_enable}[vout]"',
    'live part-label vertical position',
)

# The production workflow currently validates the legacy manifest labels below.
# Leave those compatibility labels untouched; the actual render is guarded here.
if "gblur=sigma=30" in source or "gblur=sigma=24" in source:
    raise SystemExit('Blurred side-fill removal guard failed.')
if "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" not in source:
    raise SystemExit('Solid black pillarbox guard failed.')
if "y=290" not in source or "y=400" not in source or "y=500" not in source or "y=650" not in source:
    raise SystemExit('Title/part placement guard failed.')

exec(compile(source, BASE_PATH, 'exec'), {'__name__': '__main__'})
