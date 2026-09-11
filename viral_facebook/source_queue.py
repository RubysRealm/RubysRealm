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

# Source only. Do not generate. Tight focus on current AI-brainrot style.
BRAINROT_TERMS = [
    "brainrot", "italian brainrot", "ai brainrot", "ai bird",
    "ai animal", "ai fruit", "fruit people", "ai meme",
    "surreal ai", "funny ai",
]

BRAINROT_MARKERS = [
    "brainrot", "brain rot", "italian brainrot", "ai brainrot",
    "ai bird", "ai birds", "ai animal", "ai animals",
    "ai fruit", "fruit head", "fruit people", "fruit person",
    "ai character", "ai characters", "ai story", "ai stories",
    "ai meme", "ai memes", "surreal ai", "weird ai",
    "funny ai", "ai comedy", "ai generated", "ai-generated", "ai animation",
]

REJECT_MARKERS = [
    "advertisement", "commercial", "sponsored", "sponsor", "promo",
    "promotion", "brand", "company", "product", "logo", "campaign",
    "trailer", "interview", "podcast", "news", "episode", "full movie",
    "movie", "film", "dvd", "television", "tv show", "music video",
    "official video", "gameplay", "review", "unboxing", "tutorial",
    "capcut", "template", "fetish", "bondage", "adult",
]


def _text(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(x) for x in value)
    if isinstance(value, dict):
        return " ".join(f"{k} {_text(v)}" for k, v in value.items())
    return str(value)


def doc_blob(doc):
    return " ".join(_text(doc.get(k)) for k in (
        "identifier", "title", "subject", "description", "creator", "collection"
    )).lower()


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


def candidate_from_doc(doc, *, trend_term="", search_term=""):
    identifier = str(doc.get("identifier") or "").strip()
    if not identifier:
        return None

    kind = base.license_kind(doc.get("licenseurl"), doc.get("rights"))
    if kind not in ("public-domain", "cc-by"):
        return None

    blob = doc_blob(doc)
    if not any(marker in blob for marker in BRAINROT_MARKERS):
        return None
    if any(marker in blob for marker in REJECT_MARKERS):
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
    if age_days > 900:
        return None

    popularity = min(900.0, math.log10(downloads + 1) * 135.0)
    recency = max(0.0, 220.0 - min(220.0, age_days / 2.5))
    trend_bonus = 220.0 if trend_match else 0.0
    specificity_bonus = 70.0 if any(x in blob for x in ("bird", "fruit", "brainrot", "brain rot")) else 0.0
    score = round(popularity + recency + 220.0 + trend_bonus + specificity_bonus, 2)

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
        "search_term": search_term,
        "niche": "ai",
        "style": "brainrot-ai",
        "viral_signal": signal,
        "score": score,
    }


def build_queue():
    state = load_state()
    completed = {str(x) for x in state.get("completed") or []}
    current = state.get("current") or {}
    current_key = str((current.get("candidate") or {}).get("key") or "")
    merged = {}

    def add_docs(docs, *, trend_term="", search_term=""):
        for doc in docs:
            c = candidate_from_doc(doc, trend_term=trend_term, search_term=search_term)
            if not c or c["key"] in completed or c["key"] == current_key:
                continue
            old = merged.get(c["key"])
            if old is None or float(c["score"]) > float(old.get("score") or 0):
                merged[c["key"]] = c

    # One combined Archive query per target instead of three separate searches.
    for term in BRAINROT_TERMS:
        clean = term.replace('"', " ").strip()
        try:
            q = f'mediatype:movies AND licenseurl:* AND (title:("{clean}") OR subject:("{clean}") OR description:("{clean}"))'
            add_docs(base.archive_search(q, rows=50), search_term=clean)
        except Exception:
            pass

    try:
        trends = base.trend_terms()
    except Exception:
        trends = []
    for trend in trends[:10]:
        t = str(trend or "").lower().strip()
        if t and any(marker in t for marker in ("ai", "brainrot", "bird", "fruit")):
            clean = str(trend).replace('"', " ").strip()
            try:
                q = f'mediatype:movies AND licenseurl:* AND (title:("{clean}") OR subject:("{clean}") OR description:("{clean}"))'
                add_docs(base.archive_search(q, rows=30), trend_term=clean, search_term=clean)
            except Exception:
                pass

    candidates = sorted(merged.values(), key=lambda x: float(x.get("score") or 0), reverse=True)[:QUEUE_SIZE]
    payload = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "minimumDownloads": MIN_DOWNLOADS,
        "trendMinimumDownloads": TREND_MIN_DOWNLOADS,
        "contentFocus": ["viral-ai-brainrot", "ai-birds", "fruit-head-people", "surreal-ai-stories"],
        "rejectAdsBrands": True,
        "candidates": candidates,
    }
    QUEUE_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"queued": len(candidates), "top": candidates[:5], "generatedAt": payload["generatedAt"]}, indent=2))
    if not candidates:
        raise RuntimeError("No rights-clear viral AI-brainrot candidates met the popularity/style filters.")


if __name__ == "__main__":
    build_queue()
