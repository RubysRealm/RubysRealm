#!/usr/bin/env python3
import datetime as dt
import json
import os
from pathlib import Path

DIR = Path(__file__).resolve().parent
QUEUE_PATH = DIR / "discovery_queue.json"
STATE_PATH = DIR / "state.json"
QUEUE_SIZE = int(os.getenv("FB_DISCOVERY_QUEUE_SIZE", "40"))

# Sourced media only. Generic AI animal footage is intentionally excluded.
# ShinRegis is a STYLE REFERENCE ONLY for the Halo/comedic voiceover direction;
# source media below must carry explicit reuse rights.
COMMONS_SOURCES = [
    {
        "provider": "wikimedia-commons",
        "provider_id": "Halo_4_Xbox_MENA.webm",
        "key": "commons:Halo_4_Xbox_MENA.webm",
        "title_hint": "Halo 4 gameplay",
        "niche": "gaming",
        "style": "halo-machinima-voiceover-reference",
        "viral_signal": "halo-comedy-reel-reference",
        "score": 10000,
        "source_url": "https://commons.wikimedia.org/wiki/File%3A%D8%A5%D8%B9%D9%84%D8%A7%D9%86_%D8%A7%D8%B7%D9%84%D8%A7%D9%82_%D9%87%D9%8A%D9%84%D9%88_4_%D9%84%D8%A3%D8%AC%D9%87%D8%B2%D8%A9_%D8%A7%D9%84%D8%AD%D8%A7%D8%B3%D8%A8_%D8%A7%D9%84%D8%B4%D8%AE%D8%B5%D9%8A_-_The_Master_Chief_%D9%85%D8%AC%D9%85%D9%88%D8%B9%D8%A9.webm",
        "download_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/%D8%A5%D8%B9%D9%84%D8%A7%D9%86_%D8%A7%D8%B7%D9%84%D8%A7%D9%82_%D9%87%D9%8A%D9%84%D9%88_4_%D9%84%D8%A3%D8%AC%D9%87%D8%B2%D8%A9_%D8%A7%D9%84%D8%AD%D8%A7%D8%B3%D8%A8_%D8%A7%D9%84%D8%B4%D8%AE%D8%B5%D9%8A_-_The_Master_Chief_%D9%85%D8%AC%D9%85%D9%88%D8%B9%D8%A9.webm",
        "license_kind": "cc-by-3.0",
        "license_url": "https://creativecommons.org/licenses/by/3.0/",
        "rights": "CC BY 3.0; official Xbox MENA source video on Wikimedia Commons; attribution required",
        "creator": "Xbox MENA",
        "duration_hint": 122.0,
        "reference_creator": "ShinRegis",
        "reference_url": "https://www.facebook.com/ShinRegis/reels",
    },
    {
        "provider": "wikimedia-commons",
        "provider_id": "OpenArena_0.8.8_gameplay.webm",
        "key": "commons:OpenArena_0.8.8_gameplay.webm",
        "title_hint": "fast arena shooter gameplay",
        "niche": "gaming",
        "style": "arena-shooter-fallback",
        "viral_signal": "fast-gameplay-short-form",
        "score": 4600,
        "source_url": "https://commons.wikimedia.org/wiki/File:OpenArena_0.8.8_gameplay.webm",
        "download_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/OpenArena_0.8.8_gameplay.webm",
        "license_kind": "gpl-3.0",
        "license_url": "https://www.gnu.org/licenses/gpl-3.0.html",
        "rights": "GPLv3 gameplay footage; uploader waived extra footage rights",
        "creator": "Wikimedia Commons uploader / OpenArena",
        "duration_hint": 99.0,
    },
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

def build_queue():
    state = load_state()
    completed = {str(x) for x in state.get("completed") or []}
    current = state.get("current") or {}
    current_key = str((current.get("candidate") or {}).get("key") or "")
    candidates = [
        dict(item)
        for item in COMMONS_SOURCES
        if item["key"] not in completed and item["key"] != current_key
    ][:QUEUE_SIZE]
    payload = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "contentFocus": [
            "halo-gameplay",
            "halo-machinima",
            "comedic-gaming-voiceover-style",
            "short-form-reels",
        ],
        "referenceCreator": "ShinRegis",
        "referenceUrl": "https://www.facebook.com/ShinRegis/reels",
        "referenceUse": "style-only",
        "sourceMode": "sourced-only",
        "rejectAdsBrands": True,
        "rejectGenericAIAnimals": True,
        "rejectGenericUnrelatedGaming": True,
        "candidates": candidates,
    }
    QUEUE_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"queued": len(candidates), "top": candidates[:3]}, indent=2))
    if not candidates:
        raise RuntimeError("No unused qualifying Halo-style sourced gaming candidates are currently available.")

if __name__ == "__main__":
    build_queue()
