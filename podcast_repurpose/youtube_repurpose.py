#!/usr/bin/env python3
import json
import os
import subprocess
import time
from pathlib import Path

import repurpose as base

# Keep YouTube progress completely separate from the existing TikTok queue.
base.STATE_PATH = base.DIR / "youtube_state.json"
base.TARGET = int(os.getenv("YOUTUBE_PART_TARGET_SECONDS", "165"))
base.MIN_PART = int(os.getenv("YOUTUBE_PART_MIN_SECONDS", "105"))
base.MAX_PART = int(os.getenv("YOUTUBE_PART_MAX_SECONDS", "178"))


def youtube_metadata(url):
    """Retry Dailymotion metadata independently of the TikTok pipeline."""
    last_error = None
    for attempt in range(1, 4):
        try:
            raw = base.run([
                "yt-dlp", "--dump-single-json", "--no-playlist",
                "--retries", "5", "--fragment-retries", "10",
                "--socket-timeout", "30", url,
            ], capture=True)
            data = json.loads(raw)
            if float(data.get("duration") or 0) <= 0:
                raise RuntimeError("Source video duration is unavailable")
            return data
        except Exception as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 * attempt)
    raise RuntimeError(f"YouTube source metadata failed after retries: {last_error}")


def youtube_segment_plan(duration, chapters):
    """Preserve normal chronology while guaranteeing every YouTube part stays under MAX_PART."""
    duration = float(duration)
    if duration <= base.MAX_PART:
        return [(0.0, duration)]

    boundaries = {0.0, duration}
    for c in chapters or []:
        try:
            s = float(c.get("start_time"))
        except (TypeError, ValueError):
            continue
        if 0 < s < duration:
            boundaries.add(s)
    boundaries = sorted(boundaries)

    out = []
    start = 0.0
    while duration - start > base.MAX_PART:
        remaining = duration - start

        # The shared TikTok planner can absorb a small tail into the previous
        # part, which is fine there but can create a >180s YouTube Short.
        # When only two Shorts remain, split the remainder evenly instead.
        if remaining <= 2 * base.MAX_PART:
            end = start + (remaining / 2.0)
        else:
            lo = start + base.MIN_PART
            hi = min(start + base.MAX_PART, duration)
            candidates = [b for b in boundaries if lo <= b <= hi]
            if candidates:
                ideal = start + base.TARGET
                end = min(candidates, key=lambda b: abs(b - ideal))
            else:
                end = min(start + base.TARGET, hi)

        if end <= start:
            raise RuntimeError("YouTube segment planner failed to advance")
        if end - start > base.MAX_PART + 0.01:
            raise RuntimeError("YouTube segment planner exceeded maximum part length")
        out.append((start, end))
        start = end

    if duration - start > 1.0:
        out.append((start, duration))

    for s, e in out:
        part_len = e - s
        if part_len > base.MAX_PART + 0.01:
            raise RuntimeError(f"YouTube part exceeds configured maximum: {part_len:.1f}s")
        if part_len < 30:
            raise RuntimeError(f"YouTube part is too short: {part_len:.1f}s")
    return out


def youtube_download_source(url):
    """Use several Dailymotion-safe format paths so rendition changes cannot stall YouTube."""
    for p in base.WORK.glob("source.*"):
        p.unlink(missing_ok=True)

    formats = [
        "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
        "bv*+ba/b",
        "best[height<=720]/best",
        "best",
    ]
    errors = []

    for fmt in formats:
        for p in base.WORK.glob("source.*"):
            p.unlink(missing_ok=True)
        try:
            base.run([
                "yt-dlp", "--no-playlist", "--no-progress",
                "--retries", "5", "--fragment-retries", "10",
                "--retry-sleep", "fragment:2", "--socket-timeout", "30",
                "--concurrent-fragments", "8",
                "-f", fmt,
                "--merge-output-format", "mp4",
                "--remux-video", "mp4",
                "-o", str(base.WORK / "source.%(ext)s"),
                url,
            ])
            candidates = [p for p in base.WORK.glob("source.*") if p.is_file()]
            if not candidates:
                raise RuntimeError("download produced no file")
            source = max(candidates, key=lambda p: p.stat().st_size)
            if source.stat().st_size < 500_000:
                raise RuntimeError(f"downloaded source is unexpectedly small: {source.stat().st_size} bytes")
            info = base.probe(source)
            if info["duration"] <= 0 or info["width"] <= 0 or info["height"] <= 0:
                raise RuntimeError(f"downloaded source failed validation: {info}")
            print(f"YouTube source recovered with format: {fmt}")
            return source
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            errors.append(f"{fmt}: {exc}")

    raise RuntimeError("All YouTube Dailymotion download fallbacks failed: " + " | ".join(errors))


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


base.metadata = youtube_metadata
base.segment_plan = youtube_segment_plan
base.download_source = youtube_download_source
base.render_part = render_part
base.main()
