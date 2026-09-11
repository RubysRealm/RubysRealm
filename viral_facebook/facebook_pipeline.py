#!/usr/bin/env python3
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import discover_and_render as base
import source_queue

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "viral_facebook"
WORK = DIR / "work"
OUT = DIR / "output"
STATE_PATH = DIR / "state.json"
QUEUE_PATH = DIR / "discovery_queue.json"

MIN_SHORT_SIDE = int(os.getenv("FB_MIN_SOURCE_SHORT_SIDE", "360"))
MIN_LONG_SIDE = int(os.getenv("FB_MIN_SOURCE_LONG_SIDE", "640"))
MIN_BYTES_PER_SECOND = int(os.getenv("FB_MIN_SOURCE_BYTES_PER_SECOND", "45000"))
MAX_CANDIDATE_TRIES = int(os.getenv("FB_MAX_CANDIDATE_TRIES", "18"))


def run(cmd, capture=False):
    p = subprocess.run(cmd, text=True, capture_output=capture, check=True)
    return p.stdout if capture else ""


def load_queue():
    if not QUEUE_PATH.exists():
        source_queue.build_queue()
    try:
        payload = json.loads(QUEUE_PATH.read_text())
    except Exception:
        source_queue.build_queue()
        payload = json.loads(QUEUE_PATH.read_text())
    candidates = payload.get("candidates") or []
    if not candidates:
        source_queue.build_queue()
        payload = json.loads(QUEUE_PATH.read_text())
        candidates = payload.get("candidates") or []
    return payload, candidates


def candidate_is_viral(candidate):
    if candidate.get("niche") not in ("ai", "funny"):
        return False
    try:
        downloads = int(candidate.get("downloads") or 0)
    except Exception:
        downloads = 0
    trend = bool(candidate.get("trend_term"))
    if downloads >= source_queue.MIN_DOWNLOADS:
        return True
    return trend and downloads >= source_queue.TREND_MIN_DOWNLOADS


def source_quality_ok(path, info):
    w = int(info.get("width") or 0)
    h = int(info.get("height") or 0)
    short = min(w, h)
    long = max(w, h)
    duration = float(info.get("duration") or 0)
    if short < MIN_SHORT_SIDE or long < MIN_LONG_SIDE:
        return False, f"resolution {w}x{h} below minimum"
    if duration <= 0:
        return False, "invalid duration"
    bytes_per_second = path.stat().st_size / duration
    if bytes_per_second < MIN_BYTES_PER_SECOND:
        return False, f"bitrate proxy too low ({int(bytes_per_second)} B/s)"
    return True, "ok"


def select_source(state):
    current = state.get("current")
    if current and current.get("candidate"):
        candidate = current["candidate"]
        if candidate.get("niche") not in ("ai", "funny"):
            state["current"] = None
            base.save_state(state)
        else:
            source = base.download(candidate)
            info = base.probe(source)
            ok, reason = source_quality_ok(source, info)
            if not ok:
                raise RuntimeError(f"Locked Facebook source no longer passes quality: {reason}")
            return candidate, source, info, int(current.get("next_part") or 1), True

    completed = {str(x) for x in state.get("completed") or []}
    _, queue = load_queue()
    errors = []

    for queued in queue[:MAX_CANDIDATE_TRIES]:
        if str(queued.get("key") or "") in completed:
            continue
        try:
            if not candidate_is_viral(queued):
                continue
            candidate = base.resolve_candidate(queued)
            if not candidate:
                continue
            candidate.setdefault("downloads", queued.get("downloads"))
            candidate.setdefault("trend_term", queued.get("trend_term"))
            candidate.setdefault("viral_signal", queued.get("viral_signal"))
            candidate.setdefault("score", queued.get("score"))
            candidate.setdefault("niche", queued.get("niche"))
            if candidate.get("niche") not in ("ai", "funny"):
                continue
            if candidate.get("license_kind") not in ("public-domain", "cc-by"):
                continue
            source = base.download(candidate)
            info = base.probe(source)
            ok, reason = source_quality_ok(source, info)
            if not ok:
                errors.append(f"{candidate.get('key')}: {reason}")
                continue
            return candidate, source, info, 1, False
        except Exception as e:
            errors.append(f"{queued.get('key')}: {e}")

    raise RuntimeError("No queued viral AI/funny source passed rights and quality checks. " + "; ".join(errors[-6:]))


def render_clean(source, part_index, segments):
    start, end = segments[part_index - 1]
    duration = max(1.0, end - start)
    out = OUT / f"facebook-part-{part_index:02d}-of-{len(segments):02d}.mp4"

    vf = (
        "[0:v]split=2[bg0][fg0];"
        "[bg0]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=34[bg];"
        "[fg0]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
    )
    run([
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
        "-filter_complex", vf,
        "-map", "[v]", "-map", "0:a?",
        "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(out),
    ])
    info = base.probe(out)
    if info["width"] != 1080 or info["height"] != 1920:
        raise RuntimeError("Rendered video dimensions are invalid.")
    return out, info, start, end


def post_description(candidate, part, total):
    niche = candidate.get("niche")
    if niche == "ai":
        lines = ["AI is getting out of hand 😂"]
        tags = "#ai #aivideo #funny #viral"
    else:
        lines = ["This got me 😂"]
        tags = "#funny #comedy #viral #lol"

    if total > 1:
        lines += ["", f"Part {part} of {total}"]

    lines += ["", tags]
    return "\n".join(lines).strip()


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    state = base.load_state()
    candidate, source, source_info, part_index, continuing = select_source(state)
    segments = base.segment_plan(source_info["duration"])
    if part_index < 1 or part_index > len(segments):
        part_index = 1

    video, out_info, start, end = render_clean(source, part_index, segments)
    try:
        downloads = int(candidate.get("downloads") or 0)
    except Exception:
        downloads = 0

    evidence = {
        "provider": candidate.get("provider"),
        "providerId": candidate.get("provider_id"),
        "sourceUrl": candidate.get("source_url"),
        "downloadUrl": candidate.get("download_url"),
        "creator": candidate.get("creator"),
        "licenseKind": candidate.get("license_kind"),
        "licenseUrl": candidate.get("license_url"),
        "rights": candidate.get("rights"),
        "viralSignal": candidate.get("viral_signal"),
        "contentNiche": candidate.get("niche"),
        "discoveredTrend": candidate.get("trend_term") or None,
        "score": candidate.get("score"),
        "downloads": downloads,
        "sourceWidth": source_info.get("width"),
        "sourceHeight": source_info.get("height"),
        "sourceDuration": round(float(source_info.get("duration") or 0), 3),
        "capturedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    title = base.safe_text(candidate.get("title") or candidate.get("title_hint"), "Trending video")
    manifest = {
        "pipeline": "rubysrealm-autonomous-viral-ai-funny-facebook-v3",
        "sourceKey": candidate["key"],
        "title": title,
        "part": part_index,
        "totalParts": len(segments),
        "segmentStart": round(start, 3),
        "segmentEnd": round(end, 3),
        "durationSeconds": round(out_info["duration"], 3),
        "width": out_info["width"],
        "height": out_info["height"],
        "file": video.name,
        "postDescription": post_description(candidate, part_index, len(segments)),
        "rightsEvidence": evidence,
        "qualityPassed": True,
        "viralThresholdPassed": True,
        "contentFocusPassed": True,
        "cleanVideoNoOverlayText": True,
        "sourceCreditShownInDescription": False,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (OUT / "rights-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")

    if not continuing:
        state["current"] = {
            "candidate": candidate,
            "next_part": 1,
            "total_parts": len(segments),
        }
        base.save_state(state)

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise
