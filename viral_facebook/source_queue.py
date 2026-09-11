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
# These gaming clips are hosted on Wikimedia Commons with explicit reuse licenses.
COMMONS_SOURCES = [
    {
        "provider": "wikimedia-commons",
        "provider_id": "Fallout_4_gameplay_clip.webm",
        "key": "commons:Fallout_4_gameplay_clip.webm",
        "title_hint": "Fallout 4 gaming clip",
        "niche": "gaming",
        "style": "viral-gaming",
        "viral_signal": "gaming-short-form",
        "score": 5000,
        "source_url": "https://commons.wikimedia.org/wiki/File:Fallout_4_gameplay_clip.webm",
        "download_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/Fallout_4_gameplay_clip.webm",
        "license_kind": "cc-by-3.0",
        "license_url": "https://creativecommons.org/licenses/by/3.0/",
        "rights": "CC BY 3.0; source attribution Xbox México",
        "creator": "Xbox México",
        "duration_hint": 17.3,
    },
    {
        "provider": "wikimedia-commons",
        "provider_id": "PAC-MAN_256_-_Let's_Play_(gameplay).webm",
        "key": "commons:PAC-MAN_256_gameplay.webm",
        "title_hint": "PAC-MAN 256 gameplay",
        "niche": "gaming",
        "style": "viral-gaming",
        "viral_signal": "gaming-short-form",
        "score": 4800,
        "source_url": "https://commons.wikimedia.org/wiki/File:PAC-MAN_256_-_Let%27s_Play_(gameplay).webm",
        "download_url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/PAC-MAN_256_-_Let%27s_Play_(gameplay).webm",
        "license_kind": "cc-by-3.0",
        "license_url": "https://creativecommons.org/licenses/by/3.0/",
        "rights": "CC BY 3.0; source attribution BANDAI NAMCO Europe",
        "creator": "BANDAI NAMCO Europe",
        "duration_hint": 60.0,
    },
    {
        "provider": "wikimedia-commons",
        "provider_id": "OpenArena_0.8.8_gameplay.webm",
        "key": "commons:OpenArena_0.8.8_gameplay.webm",
        "title_hint": "fast arena shooter gameplay",
        "niche": "gaming",
        "style": "viral-gaming-shooter",
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
    if not STATE_PATH.exists(): return {"current": None, "completed": []}
    try: state=json.loads(STATE_PATH.read_text())
    except Exception: return {"current": None, "completed": []}
    state.setdefault("current",None); state.setdefault("completed",[]); return state

def build_queue():
    state=load_state(); completed={str(x) for x in state.get("completed") or []}
    current=state.get("current") or {}; current_key=str((current.get("candidate") or {}).get("key") or "")
    candidates=[dict(item) for item in COMMONS_SOURCES if item["key"] not in completed and item["key"] != current_key][:QUEUE_SIZE]
    payload={"generatedAt":dt.datetime.now(dt.timezone.utc).isoformat(),"contentFocus":["viral-gaming","fast-gameplay","gaming-short-form"],"sourceMode":"sourced-only","rejectAdsBrands":True,"rejectGenericAIAnimals":True,"candidates":candidates}
    QUEUE_PATH.write_text(json.dumps(payload,indent=2)+"\n")
    print(json.dumps({"queued":len(candidates),"top":candidates[:3]},indent=2))
    if not candidates: raise RuntimeError("No unused qualifying sourced gaming candidates are currently available.")

if __name__ == "__main__": build_queue()
