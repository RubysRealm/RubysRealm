#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "podcast_repurpose"
WORK = DIR / "work"
OUT = DIR / "output"
STATE_PATH = DIR / "state.json"
SOURCE_CHANNEL = os.getenv(
    "PODCAST_VIDEO_SOURCE",
    "https://www.dailymotion.com/user/MasterPOVYT/videos",
).strip()
TARGET = int(os.getenv("PART_TARGET_SECONDS", "180"))
MIN_PART = int(os.getenv("PART_MIN_SECONDS", "105"))
MAX_PART = int(os.getenv("PART_MAX_SECONDS", "220"))


def run(cmd, capture=False):
    p = subprocess.run(cmd, text=True, capture_output=capture, check=True)
    return p.stdout if capture else ""


def load_state():
    if not STATE_PATH.exists():
        return {"current": None, "completed": []}
    data = json.loads(STATE_PATH.read_text())
    data.setdefault("current", None)
    data.setdefault("completed", [])
    return data


def canonical_url(entry):
    url = entry.get("webpage_url") or entry.get("url") or ""
    if str(url).startswith("http"):
        return str(url)
    vid = entry.get("id") or url
    if vid:
        return f"https://www.dailymotion.com/video/{vid}"
    return ""


def catalog():
    raw = run([
        "yt-dlp", "--flat-playlist", "--dump-single-json",
        "--playlist-end", "100", SOURCE_CHANNEL,
    ], capture=True)
    data = json.loads(raw)
    items = []
    for e in data.get("entries") or []:
        url = canonical_url(e)
        if not url:
            continue
        items.append({
            "id": str(e.get("id") or url.rsplit("/", 1)[-1]),
            "title": str(e.get("title") or "Master POV"),
            "url": url,
        })
    if not items:
        raise RuntimeError("No source videos were discovered")
    return items


def metadata(url):
    raw = run(["yt-dlp", "--dump-single-json", "--no-playlist", url], capture=True)
    return json.loads(raw)


def enforce_story_lock(state, selected):
    current = state.get("current") or {}
    locked_id = current.get("id")
    if locked_id and selected.get("id") != locked_id:
        raise RuntimeError(f"Story lock violation: active story {locked_id}, attempted {selected.get('id')}")
    return selected

def choose_episode(state, items):
    current = state.get("current")
    if current and current.get("id"):
        for item in items:
            if item["id"] == current["id"]:
                return enforce_story_lock(state, item), int(current.get("next_part") or 1)
        # Keep working a current episode even if it dropped off the first page.
        if current.get("url"):
            return {
                "id": current["id"],
                "title": current.get("title") or "Master POV",
                "url": current["url"],
            }, int(current.get("next_part") or 1)

    completed = set(state.get("completed") or [])
    for item in items:  # Source listing is newest-first.
        if item["id"] not in completed:
            return item, 1
    raise RuntimeError("All discovered source videos have already been completed")


def segment_plan(duration, chapters):
    duration = float(duration)
    if duration <= MAX_PART:
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
    while duration - start > MAX_PART:
        lo = start + MIN_PART
        hi = min(start + MAX_PART, duration)
        candidates = [b for b in boundaries if lo <= b <= hi]
        if candidates:
            ideal = start + TARGET
            end = min(candidates, key=lambda b: abs(b - ideal))
        else:
            end = min(start + TARGET, duration)
        # Avoid leaving a tiny final fragment.
        if 0 < duration - end < MIN_PART:
            end = duration
        out.append((start, end))
        start = end
    if duration - start > 1.0:
        out.append((start, duration))

    if len(out) >= 2 and out[-1][1] - out[-1][0] < 70:
        prev = out[-2]
        out[-2] = (prev[0], out[-1][1])
        out.pop()
    return out


def download_source(url):
    for p in WORK.glob("source.*"):
        p.unlink()
    run([
        "yt-dlp", "--no-playlist",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", str(WORK / "source.%(ext)s"),
        url,
    ])
    candidates = [p for p in WORK.glob("source.*") if p.is_file()]
    if not candidates:
        raise RuntimeError("Source video download did not produce a file")
    return max(candidates, key=lambda p: p.stat().st_size)


def safe_title(title):
    title = re.sub(r"\s+", " ", title).strip()
    lines = textwrap.wrap(title, width=34, break_long_words=False, break_on_hyphens=False)
    if len(lines) > 2:
        lines = lines[:2]
        if len(lines[-1]) > 3:
            lines[-1] = lines[-1][:-3].rstrip() + "..."
    return "\n".join(lines) or "Master POV"


def probe(path):
    raw = run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json", str(path),
    ], capture=True)
    d = json.loads(raw)
    stream = (d.get("streams") or [{}])[0]
    return {
        "duration": float((d.get("format") or {}).get("duration") or 0),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
    }


def render_part(source, title, index, total, start, end, dest):
    title_file = WORK / "title.txt"
    part_file = WORK / "part.txt"
    title_file.write_text(safe_title(title))
    part_file.write_text(f"PART {index} OF {total}")
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    dur = max(1.0, end - start)
    vf = (
        "[0:v]split=2[bg0][fg0];"
        "[bg0]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=32[bg];"
        "[fg0]scale=1000:1000:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2+160[base];"
        "[base]drawbox=x=45:y=430:w=990:h=300:color=black@0.60:t=fill,"
        f"drawtext=fontfile={font}:textfile={title_file.as_posix()}:"
        "fontcolor=white:fontsize=44:line_spacing=12:x=(w-text_w)/2:y=465,"
        f"drawtext=fontfile={font}:textfile={part_file.as_posix()}:"
        "fontcolor=white:fontsize=50:x=(w-text_w)/2:y=635[v]"
    )
    run([
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(source),
        "-filter_complex", vf,
        "-map", "[v]", "-map", "0:a?",
        "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(dest),
    ])


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    state = load_state()
    items = catalog()
    episode, next_part = choose_episode(state, items)
    meta = metadata(episode["url"])
    title = str(meta.get("title") or episode["title"] or "Master POV")
    duration = float(meta.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("Source video duration is unavailable")
    segments = segment_plan(duration, meta.get("chapters") or [])
    if next_part < 1 or next_part > len(segments):
        next_part = 1

    source = download_source(episode["url"])
    start, end = segments[next_part - 1]
    dest = OUT / f"{episode['id']}-part-{next_part:02d}-of-{len(segments):02d}.mp4"
    render_part(source, title, next_part, len(segments), start, end, dest)
    info = probe(dest)
    if info["width"] != 1080 or info["height"] != 1920:
        raise RuntimeError(f"Bad output dimensions: {info['width']}x{info['height']}")
    if info["duration"] < 60:
        raise RuntimeError(f"Part is unexpectedly short: {info['duration']:.1f}s")

    manifest = {
        "pipeline": "rubys-realm-podcast-repurpose-v1",
        "source": {
            "catalog": SOURCE_CHANNEL,
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
        "video": str(dest.relative_to(ROOT)),
        "qualityPassed": True,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
