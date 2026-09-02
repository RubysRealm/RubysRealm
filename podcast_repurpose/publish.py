#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "podcast_repurpose"
OUT = DIR / "output"
STATE_PATH = DIR / "state.json"
API = "https://open.tiktokapis.com"


def post(path, token, body):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=UTF-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:1200]
        raise RuntimeError(f"TikTok API HTTP {e.code}: {body}") from e
    err = payload.get("error") or {}
    if err.get("code") not in (None, "", "ok"):
        raise RuntimeError(str(err))
    return payload.get("data") or {}


def load_manifest():
    p = OUT / "manifest.json"
    if not p.exists():
        raise RuntimeError("Repurpose manifest is missing")
    d = json.loads(p.read_text())
    if d.get("pipeline") != "rubys-realm-podcast-repurpose-v1":
        raise RuntimeError("Wrong repurpose pipeline manifest")
    if not d.get("qualityPassed"):
        raise RuntimeError("Repurpose quality gate did not pass")
    video = ROOT / str(d.get("video") or "")
    if not video.exists() or video.stat().st_size < 100000:
        raise RuntimeError("Prepared video is missing or too small")
    if int(d.get("width") or 0) != 1080 or int(d.get("height") or 0) != 1920:
        raise RuntimeError("Prepared video is not 1080x1920")
    return d, video


def upload_chunks(upload_url, video):
    size = video.stat().st_size
    chunk_size = min(size, 32 * 1024 * 1024)
    total_chunks = (size + chunk_size - 1) // chunk_size
    with video.open("rb") as f:
        for i in range(total_chunks):
            start = i * chunk_size
            data = f.read(chunk_size)
            end = start + len(data) - 1
            req = urllib.request.Request(
                upload_url,
                data=data,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(data)),
                    "Content-Range": f"bytes {start}-{end}/{size}",
                },
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=300) as r:
                r.read()
    return chunk_size, total_chunks


def update_state(manifest):
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text())
    else:
        state = {"current": None, "completed": []}
    src = manifest["source"]
    part = int(manifest["part"])
    total = int(manifest["totalParts"])
    completed = list(state.get("completed") or [])
    if part >= total:
        if src["id"] not in completed:
            completed.append(src["id"])
        state["completed"] = completed[-500:]
        state["current"] = None
    else:
        state["current"] = {
            "id": src["id"],
            "url": src["url"],
            "title": src["title"],
            "next_part": part + 1,
            "total_parts": total,
        }
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def main():
    token = os.environ.get("TT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TikTok authorization secret TT_TOKEN is not configured")

    manifest, video = load_manifest()
    creator = post("/v2/post/publish/creator_info/query/", token, {})
    privacy_options = creator.get("privacy_level_options") or []
    if "PUBLIC_TO_EVERYONE" not in privacy_options:
        raise RuntimeError(f"TikTok connection cannot currently publish publicly: {privacy_options}")

    title = str(manifest["source"]["title"])
    part = int(manifest["part"])
    total = int(manifest["totalParts"])
    caption = f"{title} | Part {part}/{total} #storytime #pov #rubysrealm"
    if len(caption) > 2150:
        caption = caption[:2147] + "..."

    size = video.stat().st_size
    chunk_size = min(size, 32 * 1024 * 1024)
    total_chunks = (size + chunk_size - 1) // chunk_size
    init = post(
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
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunks,
            },
        },
    )
    upload_url = init["upload_url"]
    publish_id = init["publish_id"]
    upload_chunks(upload_url, video)

    final = None
    for _ in range(60):
        status = post("/v2/post/publish/status/fetch/", token, {"publish_id": publish_id})
        state = str(status.get("status") or status.get("publish_status") or "").upper()
        if state in ("PUBLISH_COMPLETE", "SUCCESS", "COMPLETED", "POSTED"):
            final = status
            break
        if state in ("FAILED", "PUBLISH_FAILED", "ERROR"):
            raise RuntimeError(str(status))
        time.sleep(10)
    if final is None:
        raise RuntimeError(f"TikTok publish was not confirmed in time: {publish_id}")

    update_state(manifest)
    result = {
        "published": True,
        "publishId": publish_id,
        "title": title,
        "part": part,
        "totalParts": total,
        "status": final,
    }
    (OUT / "publish-result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise
