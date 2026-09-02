#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = ROOT / "tiktok_animator" / "podcast_queue.json"
STATE_PATH = ROOT / "tiktok_animator" / "podcast_state.json"
TIKTOK_ROOT = "https://open.tiktokapis.com"
TZ = ZoneInfo("America/New_York")


def load_json(path):
    return json.loads(path.read_text())


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def api_post(path, token, body):
    req = urllib.request.Request(
        TIKTOK_ROOT + path,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=UTF-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        payload = json.loads(r.read().decode())
    err = payload.get("error") or {}
    if err.get("code") not in (None, "", "ok"):
        raise RuntimeError(f"TikTok API error: {err}")
    return payload.get("data") or {}


def ensure_active_story(queue, state):
    today = datetime.now(TZ).date().isoformat()
    stories = queue["stories"]
    idx = int(state.get("story_index", 0))
    if idx >= len(stories):
        print("No queued stories remain.")
        return None, None, None

    story = stories[idx]
    parts = story["parts"]
    next_part = int(state.get("next_part", 1))
    story_day = state.get("story_day")

    if story_day is None:
        state["story_day"] = today
        story_day = today
        save_json(STATE_PATH, state)

    if next_part > len(parts):
        if story["id"] not in state.get("completed_story_ids", []):
            state.setdefault("completed_story_ids", []).append(story["id"])
            save_json(STATE_PATH, state)
        if today == story_day:
            print(f"{story['title']} is complete for {today}; waiting until the next day.")
            return None, None, None
        idx += 1
        if idx >= len(stories):
            print("Current story is complete and no next story is queued yet.")
            return None, None, None
        state["story_index"] = idx
        state["next_part"] = 1
        state["story_day"] = today
        state["last_publish_id"] = None
        story = stories[idx]
        parts = story["parts"]
        next_part = 1
        save_json(STATE_PATH, state)

    # If a story was not completed during its intended calendar day, it remains
    # locked until completion. We never mix a second story into that backlog day.
    part = parts[next_part - 1]
    return story, part, len(parts)


def download_source(source_url, work):
    template = str(work / "source.%(ext)s")
    subprocess.run(
        [
            "yt-dlp",
            "--no-playlist",
            "--merge-output-format", "mp4",
            "-f", "bv*+ba/b",
            "-o", template,
            source_url,
        ],
        check=True,
    )
    candidates = sorted(work.glob("source.*"))
    if not candidates:
        raise RuntimeError("Source video download produced no file")
    return candidates[0]


def render_part(source, part, output):
    start = float(part["start"])
    end = float(part["end"])
    if end <= start:
        raise RuntimeError(f"Bad part range: {start}..{end}")

    vf = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=24[bg2];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-ss", f"{start:.3f}",
            "-to", f"{end:.3f}",
            "-i", str(source),
            "-filter_complex", vf,
            "-map", "[v]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-r", "30",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output),
        ],
        check=True,
    )
    if not output.exists() or output.stat().st_size < 100_000:
        raise RuntimeError("Rendered TikTok part is missing or unexpectedly small")


def caption_for(story, part, total):
    return (
        f"{story['title']} — Part {part['number']}/{total}: {part['label']} "
        "#storytime #storytok #pov #rubysrealm"
    )


def publish(video, caption, token):
    creator = api_post("/v2/post/publish/creator_info/query/", token, {})
    privacy_options = creator.get("privacy_level_options") or []
    if "PUBLIC_TO_EVERYONE" not in privacy_options:
        raise RuntimeError(f"Public TikTok posting is not available for this authorization: {privacy_options}")

    size = video.stat().st_size
    init = api_post(
        "/v2/post/publish/video/init/",
        token,
        {
            "post_info": {
                "title": caption,
                "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        },
    )
    upload_url = init["upload_url"]
    publish_id = init["publish_id"]
    data = video.read_bytes()
    req = urllib.request.Request(
        upload_url,
        data=data,
        headers={
            "Content-Type": "video/mp4",
            "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size-1}/{size}",
        },
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        r.read()

    for _ in range(90):
        status = api_post("/v2/post/publish/status/fetch/", token, {"publish_id": publish_id})
        state = (status.get("status") or status.get("publish_status") or "").upper()
        if state in ("PUBLISH_COMPLETE", "SUCCESS", "COMPLETED", "POSTED"):
            return publish_id
        if state in ("FAILED", "PUBLISH_FAILED", "ERROR"):
            raise RuntimeError(f"TikTok publish failed: {status}")
        time.sleep(10)
    raise RuntimeError(f"TikTok publish did not confirm completion for {publish_id}; part counter was NOT advanced")


def main():
    token = os.environ.get("TT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TT_TOKEN is not configured")

    queue = load_json(QUEUE_PATH)
    state = load_json(STATE_PATH)
    story, part, total = ensure_active_story(queue, state)
    if story is None:
        return 0

    expected = int(state.get("next_part", 1))
    if int(part["number"]) != expected:
        raise RuntimeError(f"Ordering lock failed: expected Part {expected}, got Part {part['number']}")

    print(f"Locked story: {story['title']}")
    print(f"Publishing Part {part['number']}/{total}: {part['label']}")

    with tempfile.TemporaryDirectory(prefix="rubys-podcast-") as td:
        work = Path(td)
        source = download_source(story["source_url"], work)
        output = work / f"part-{part['number']:02d}.mp4"
        render_part(source, part, output)
        caption = caption_for(story, part, total)
        print("Caption:", caption)
        publish_id = publish(output, caption, token)

    # Advance only after TikTok explicitly confirms this exact part completed.
    state["last_publish_id"] = publish_id
    state["last_published_at"] = datetime.now(TZ).isoformat()
    state["next_part"] = expected + 1
    save_json(STATE_PATH, state)
    print(f"Published Part {expected}/{total}; next allowed part is {state['next_part']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
