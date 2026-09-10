#!/usr/bin/env python3
import os
from pathlib import Path

import repurpose as base

# Keep YouTube progress completely separate from the existing TikTok queue.
base.STATE_PATH = base.DIR / "youtube_state.json"
base.TARGET = int(os.getenv("YOUTUBE_PART_TARGET_SECONDS", "165"))
base.MIN_PART = int(os.getenv("YOUTUBE_PART_MIN_SECONDS", "105"))
base.MAX_PART = int(os.getenv("YOUTUBE_PART_MAX_SECONDS", "178"))


def render_part(source, title, index, total, start, end, dest):
    title_file = base.WORK / "title.txt"
    part_file = base.WORK / "part.txt"
    title_file.write_text(base.safe_title(title))
    part_file.write_text(f"PART {index} OF {total}")
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    dur = max(1.0, end - start)

    info = base.probe(source)
    sw = max(1, info["width"])
    sh = max(1, info["height"])
    scale = min(1000.0 / sw, 1000.0 / sh)
    foreground_height = sh * scale
    picture_top = (1920.0 - foreground_height) / 2.0 + 160.0
    gap_midpoint = picture_top / 2.0

    box_h = 260
    box_y = max(35, int(round(gap_midpoint - box_h / 2.0)))
    title_y = box_y + 34
    part_y = box_y + 180

    vf = (
        "[0:v]split=2[bg0][fg0];"
        "[bg0]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=32[bg];"
        "[fg0]scale=1000:1000:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2+160[base];"
        f"[base]drawbox=x=45:y={box_y}:w=990:h={box_h}:color=black@0.60:t=fill,"
        f"drawtext=fontfile={font}:textfile={title_file.as_posix()}:"
        f"fontcolor=white:fontsize=44:line_spacing=12:x=(w-text_w)/2:y={title_y},"
        f"drawtext=fontfile={font}:textfile={part_file.as_posix()}:"
        f"fontcolor=white:fontsize=50:x=(w-text_w)/2:y={part_y}[v]"
    )
    base.run([
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(source),
        "-filter_complex", vf,
        "-map", "[v]", "-map", "0:a?",
        "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(dest),
    ])


base.render_part = render_part
base.main()
