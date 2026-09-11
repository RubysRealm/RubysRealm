#!/usr/bin/env python3
import datetime as dt
import json
import math
import os
from pathlib import Path

import discover_and_render as base

DIR = Path(__file__).resolve().parent
QUEUE_PATH = DIR / "discovery_queue.json"
STATE_PATH = DIR / "state.json"

MIN_DOWNLOADS = int(os.getenv("FB_MIN_VIRAL_DOWNLOADS", "10000"))
TREND_MIN_DOWNLOADS = int(os.getenv("FB_TREND_MIN_DOWNLOADS", "1000"))
QUEUE_SIZE = int(os.getenv("FB_DISCOVERY_QUEUE_SIZE", "40"))

NICHES = [
    "funny", "animals", "wildlife", "fails", "amazing",
    "caught on camera", "dashcam", "satisfying", "sports", "unexpected",
]


def load_state():
    if not STATE_PATH.exists():
        return {"current": None, "completed": []}
    try:
        state = json.loads(STATE_PATH.read_text())
    except Exception:
        return {"current": None, "completed": []}
    state.setdefault("current", None)
    state.setdefault("completed", [])
    return state


def candidate_from_doc(doc, *, trend_term="", niche=""):
    identifier = str(doc.get("identifier") or "").strip()
    if not identifier:
        return None

    kind = base.license_kind(doc.get("licenseurl"), doc.get("rights"))
    if kind not in ("public-domain", "cc-by"):
        return None

    try:
        downloads = int(doc.get("downloads") or 0)
    except Exception:
        downloads = 0

    trend_match = bool(trend_term)
    if trend_match:
        if downloads < TREND_MIN_DOWNLOADS:
            return None
    elif downloads < MIN_DOWNLOADS:
        return None

    age_days = base.parse_iso_age_days(doc.get("publicdate") or doc.get("date"))
    popularity = min(900.0, math.log10(downloads + 1) * 135.0)
    recency = max(0.0, 140.0 - min(140.0, age_days / 5.0))
    trend_bonus = 280.0 if trend_match else 0.0
    niche_bonus = 90.0 if niche else 0.0
    score = round(popularity + recency + trend_bonus + niche_bonus, 2)

    if downloads >= 250000:
        signal = "high-downloads"
    elif trend_match:
        signal = "current-trend-plus-downloads"
    else:
        signal = "semi-viral-downloads"

    return {
        "provider": "internet-archive",
        "provider_id": identifier,
        "key": f"archive:{identifier}",
        "title_hint": base.safe_text(doc.get("title"), identifier),
        "downloads": downloads,
        "trend_term": trend_term,
        "niche": niche,
        "viral_signal": signal,
        "score": score,
    }


def build_queue():
    state = load_state()
    completed = {str(x) for x in state.get("completed") or []}
    current = state.get("current") or {}
    current_key = str((current.get("candidate") or {}).get("key") or "")

    trends = base.trend_terms()
    merged = {}

    def add_docs(docs, *, trend_term="", niche=""):
        for doc in docs:
            c = candidate_from_doc(doc, trend_term=trend_term, niche=niche)
            if not c:
                continue
            if c["key"] in completed or c["key"] == current_key:
                continue
            old = merged.get(c["key"])
            if old is None or float(c["score"]) > float(old.get("score") or 0):
                merged[c["key"]] = c

    for term in trends[:8]:
        clean = term.replace('"', " ").strip()
        if not clean:
            continue
        queries = [
            f'mediatype:movies AND licenseurl:* AND title:("{clean}")',
            f'mediatype:movies AND licenseurl:* AND subject:("{clean}")',
        ]
        for q in queries:
            try:
                add_docs(base.archive_search(q, rows=25), trend_term=clean)
            except Exception:
                pass

    for niche in NICHES:
        clean = niche.replace('"', " ")
        q = f'mediatype:movies AND licenseurl:* AND (title:("{clean}") OR subject:("{clean}"))'
        try:
            add_docs(base.archive_search(q, rows=20), niche=niche)
        except Exception:
            pass

    try:
        add_docs(base.archive_search("mediatype:movies AND licenseurl:*", rows=80))
    except Exception:
        pass

    candidates = sorted(merged.values(), key=lambda x: float(x.get("score") or 0), reverse=True)[:QUEUE_SIZE]
    payload = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "minimumDownloads": MIN_DOWNLOADS,
        "trendMinimumDownloads": TREND_MIN_DOWNLOADS,
        "trends": trends[:8],
        "candidates": candidates,
    }
    QUEUE_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({
        "queued": len(candidates),
        "top": candidates[:5],
        "generatedAt": payload["generatedAt"],
    }, indent=2))
    if not candidates:
        raise RuntimeError("No rights-clear viral/semi-viral candidates met the popularity threshold.")


if __name__ == "__main__":
    build_queue()
