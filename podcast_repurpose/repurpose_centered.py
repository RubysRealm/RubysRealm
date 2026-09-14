#!/usr/bin/env python3
from pathlib import Path
import json
import shutil

import repurpose as base


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


def choose_viable_story(state):
    current = state.get("current") or {}
    if current.get("id"):
        episode = {
            "id": current["id"],
            "title": current.get("title") or "Master POV",
            "url": current.get("url") or "",
        }
        if not episode["url"]:
            items = base.catalog()
            matches = [item for item in items if item["id"] == current["id"]]
            if not matches:
                raise RuntimeError(f"Active story {current['id']} is missing from the source catalog")
            episode = matches[0]
        meta = base.metadata(episode["url"])
        return episode, int(current.get("next_part") or 1), meta

    completed = set(state.get("completed") or [])
    items = base.catalog()
    failures = []
    for item in items:
        if item["id"] in completed:
            continue
        try:
            meta = base.metadata(item["url"])
            duration = float(meta.get("duration") or 0)
            if duration <= 0:
                raise RuntimeError("duration unavailable")
            return item, 1, meta
        except Exception as exc:
            failures.append(f"{item['id']}: {exc}")
            print(f"Skipping unavailable handoff candidate {item['id']} for this run: {exc}")
            continue
    detail = "; ".join(failures[:8])
    raise RuntimeError(f"No viable uncompleted source story was available. {detail}")


def main():
    shutil.rmtree(base.WORK, ignore_errors=True)
    shutil.rmtree(base.OUT, ignore_errors=True)
    base.WORK.mkdir(parents=True, exist_ok=True)
    base.OUT.mkdir(parents=True, exist_ok=True)

    state = base.load_state()
    episode, next_part, meta = choose_viable_story(state)
    title = str(meta.get("title") or episode["title"] or "Master POV")
    duration = float(meta.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("Source video duration is unavailable")

    segments = base.segment_plan(duration, meta.get("chapters") or [])
    if next_part < 1 or next_part > len(segments):
        if state.get("current"):
            raise RuntimeError(
                f"Active story state is invalid: requested part {next_part} of {len(segments)}"
            )
        next_part = 1

    source = base.download_source(episode["url"])
    start, end = segments[next_part - 1]
    dest = base.OUT / f"{episode['id']}-part-{next_part:02d}-of-{len(segments):02d}.mp4"
    render_part(source, title, next_part, len(segments), start, end, dest)
    info = base.probe(dest)
    if info["width"] != 1080 or info["height"] != 1920:
        raise RuntimeError(f"Bad output dimensions: {info['width']}x{info['height']}")
    if info["duration"] < 60:
        raise RuntimeError(f"Part is unexpectedly short: {info['duration']:.1f}s")

    manifest = {
        "pipeline": "rubys-realm-podcast-repurpose-v1",
        "source": {
            "catalog": base.SOURCE_CHANNEL,
            "id": episode["id"],
            "url": episode["url"],
            "title": title,
            "durationSeconds": round(duration, 3),
        },
        "part": next_part,
        "totalParts": len(segments),
        "segmentStart": round(start, 3),
        "segmentEnd": round(end, 3),
        "durationSeconds": round(info["duration"], 3),
        "width": info["width"],
        "height": info["height"],
        "video": str(dest.relative_to(base.ROOT)),
        "qualityPassed": True,
    }
    (base.OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


base.render_part = render_part
main()
