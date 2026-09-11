#!/usr/bin/env python3
import datetime as dt
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "viral_facebook"
WORK = DIR / "work"
OUT = DIR / "output"
STATE_PATH = DIR / "state.json"

TARGET_SECONDS = int(os.getenv("FB_PART_TARGET_SECONDS", "165"))
MAX_SECONDS = int(os.getenv("FB_PART_MAX_SECONDS", "180"))
MIN_SOURCE_SECONDS = int(os.getenv("FB_MIN_SOURCE_SECONDS", "12"))
MAX_SOURCE_SECONDS = int(os.getenv("FB_MAX_SOURCE_SECONDS", "1200"))
MAX_DOWNLOAD_BYTES = int(os.getenv("FB_MAX_DOWNLOAD_BYTES", str(500 * 1024 * 1024)))
USER_AGENT = "RubysRealmRightsClearVideoBot/1.0"

ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"
ARCHIVE_METADATA = "https://archive.org/metadata/{identifier}"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=US"

CC_BY_RE = re.compile(r"creativecommons\.org/licenses/by/(?:1\.0|2\.0|2\.5|3\.0|4\.0)", re.I)
PUBLIC_DOMAIN_MARKERS = (
    "public domain",
    "creativecommons.org/publicdomain/zero/",
    "creativecommons.org/publicdomain/mark/",
    "cc0",
)
BLOCKED_LICENSE_MARKERS = (
    "by-nc",
    "by-nd",
    "noncommercial",
    "no derivatives",
    "all rights reserved",
)


def run(cmd, capture=False):
    p = subprocess.run(cmd, text=True, capture_output=capture, check=True)
    return p.stdout if capture else ""


def http_bytes(url, timeout=45):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_json(url, params=None, timeout=45):
    if params:
        qs = urllib.parse.urlencode(params, doseq=True)
        url = url + ("&" if "?" in url else "?") + qs
    return json.loads(http_bytes(url, timeout=timeout).decode("utf-8", "replace"))


def load_state():
    if not STATE_PATH.exists():
        return {"current": None, "completed": [], "rights_history": []}
    state = json.loads(STATE_PATH.read_text())
    state.setdefault("current", None)
    state.setdefault("completed", [])
    state.setdefault("rights_history", [])
    return state


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def trend_terms():
    terms = []
    try:
        root = ET.fromstring(http_bytes(GOOGLE_TRENDS_RSS, timeout=20))
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            title = re.sub(r"\s+", " ", title)
            if 2 <= len(title) <= 80 and title.lower() not in {x.lower() for x in terms}:
                terms.append(title)
            if len(terms) >= 8:
                break
    except Exception:
        pass
    return terms


def license_kind(*values):
    text = " ".join(str(v or "") for v in values).strip()
    low = html.unescape(text).lower()
    if any(marker in low for marker in BLOCKED_LICENSE_MARKERS):
        return None
    if any(marker in low for marker in PUBLIC_DOMAIN_MARKERS):
        return "public-domain"
    if CC_BY_RE.search(low):
        return "cc-by"
    return None


def safe_text(value, default=""):
    if isinstance(value, list):
        value = ", ".join(str(x) for x in value if x)
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or default


def parse_archive_length(value):
    if not value:
        return None
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        pass
    parts = s.split(":")
    try:
        nums = [float(x) for x in parts]
    except ValueError:
        return None
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return None


def parse_iso_age_days(value):
    if not value:
        return 3650
    s = str(value).strip().replace("Z", "+00:00")
    try:
        t = dt.datetime.fromisoformat(s)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return max(0, (dt.datetime.now(dt.timezone.utc) - t).days)
    except Exception:
        return 3650


def archive_search(query, rows=30):
    params = {
        "q": query,
        "fl[]": [
            "identifier", "title", "downloads", "publicdate", "date",
            "creator", "licenseurl", "rights", "description", "subject"
        ],
        "rows": str(rows),
        "page": "1",
        "output": "json",
        "sort[]": "downloads desc",
    }
    data = http_json(ARCHIVE_SEARCH, params)
    return (data.get("response") or {}).get("docs") or []


def archive_file(identifier):
    data = http_json(ARCHIVE_METADATA.format(identifier=urllib.parse.quote(identifier, safe="")))
    meta = data.get("metadata") or {}
    kind = license_kind(meta.get("licenseurl"), meta.get("rights"), meta.get("license"))
    if not kind:
        return None

    options = []
    for f in data.get("files") or []:
        name = str(f.get("name") or "")
        if not name.lower().endswith((".mp4", ".m4v")):
            continue
        try:
            size = int(f.get("size") or 0)
        except Exception:
            size = 0
        if size and (size < 1_000_000 or size > MAX_DOWNLOAD_BYTES):
            continue
        length = parse_archive_length(f.get("length"))
        if length and (length < MIN_SOURCE_SECONDS or length > MAX_SOURCE_SECONDS):
            continue
        source_rank = 2 if str(f.get("source") or "").lower() == "original" else 1
        format_rank = 2 if "mpeg4" in str(f.get("format") or "").lower() else 1
        size_rank = 1 if 5_000_000 <= size <= 250_000_000 else 0
        options.append((source_rank + format_rank + size_rank, size, name, length))
    if not options:
        return None
    options.sort(reverse=True)
    _, size, name, length = options[0]
    return {
        "download_url": f"https://archive.org/download/{urllib.parse.quote(identifier, safe='')}/{urllib.parse.quote(name)}",
        "file_name": name,
        "file_size": size,
        "duration_hint": length,
        "license_kind": kind,
        "license_url": safe_text(meta.get("licenseurl")),
        "rights": safe_text(meta.get("rights")),
        "creator": safe_text(meta.get("creator"), "Unknown creator"),
        "title": safe_text(meta.get("title"), identifier),
        "source_url": f"https://archive.org/details/{urllib.parse.quote(identifier, safe='')}",
        "description": safe_text(meta.get("description")),
    }


def archive_candidates(terms):
    seen = set()
    out = []
    queries = []
    for term in terms[:6]:
        clean = term.replace('"', " ").strip()
        if clean:
            queries.append((f'mediatype:movies AND licenseurl:* AND title:("{clean}")', clean, 220))
            queries.append((f'mediatype:movies AND licenseurl:* AND subject:("{clean}")', clean, 160))
    queries.append(("mediatype:movies AND licenseurl:*", "", 0))

    for query, term, trend_bonus in queries:
        try:
            docs = archive_search(query, rows=25 if term else 60)
        except Exception:
            continue
        for d in docs:
            identifier = str(d.get("identifier") or "").strip()
            if not identifier or identifier in seen:
                continue
            seen.add(identifier)
            kind = license_kind(d.get("licenseurl"), d.get("rights"))
            if not kind and not d.get("licenseurl"):
                continue
            try:
                downloads = int(d.get("downloads") or 0)
            except Exception:
                downloads = 0
            age_days = parse_iso_age_days(d.get("publicdate") or d.get("date"))
            recency = max(0.0, 120.0 - min(120.0, age_days / 6.0))
            popularity = min(650.0, math.log10(downloads + 1) * 115.0)
            score = popularity + recency + trend_bonus
            out.append({
                "provider": "internet-archive",
                "provider_id": identifier,
                "key": f"archive:{identifier}",
                "title_hint": safe_text(d.get("title"), identifier),
                "downloads": downloads,
                "trend_term": term,
                "score": round(score, 2),
            })
        if len(out) >= 80:
            break
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def commons_candidates(terms):
    out = []
    seen = set()
    search_terms = terms[:4] + ["viral video", "animals", "nature", "space"]
    for term in search_terms:
        try:
            data = http_json(COMMONS_API, {
                "action": "query",
                "generator": "search",
                "gsrsearch": f"filetype:video {term}",
                "gsrnamespace": "6",
                "gsrlimit": "15",
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata",
                "format": "json",
                "formatversion": "2",
            })
        except Exception:
            continue
        pages = (data.get("query") or {}).get("pages") or []
        for p in pages:
            title = str(p.get("title") or "")
            if not title or title in seen:
                continue
            seen.add(title)
            info = ((p.get("imageinfo") or [{}])[0]) or {}
            ext = info.get("extmetadata") or {}

            def extv(name):
                v = ext.get(name) or {}
                return v.get("value") if isinstance(v, dict) else v

            kind = license_kind(extv("LicenseUrl"), extv("LicenseShortName"), extv("UsageTerms"))
            if not kind:
                continue
            mime = str(info.get("mime") or "")
            url = str(info.get("url") or "")
            try:
                size = int(info.get("size") or 0)
            except Exception:
                size = 0
            if not url or not mime.startswith("video/") or (size and size > MAX_DOWNLOAD_BYTES):
                continue
            trend_bonus = 200 if term in terms else 50
            size_score = 60 if 5_000_000 <= size <= 250_000_000 else 20
            out.append({
                "provider": "wikimedia-commons",
                "provider_id": title,
                "key": f"commons:{title}",
                "title": title.removeprefix("File:"),
                "creator": safe_text(extv("Artist"), "Wikimedia Commons contributor"),
                "license_kind": kind,
                "license_url": safe_text(extv("LicenseUrl")),
                "rights": safe_text(extv("UsageTerms")),
                "source_url": str(info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"),
                "download_url": url,
                "file_size": size,
                "description": safe_text(extv("ImageDescription")),
                "trend_term": term if term in terms else "",
                "score": float(trend_bonus + size_score),
            })
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def resolve_candidate(candidate):
    if candidate["provider"] == "internet-archive":
        details = archive_file(candidate["provider_id"])
        if not details:
            return None
        result = {**candidate, **details}
        result["key"] = candidate["key"]
        return result
    return candidate


def credit_line(candidate):
    title = safe_text(candidate.get("title") or candidate.get("title_hint"), "Video")
    creator = safe_text(candidate.get("creator"), "Unknown creator")
    source_url = safe_text(candidate.get("source_url"))
    license_url = safe_text(candidate.get("license_url"))
    if candidate.get("license_kind") == "cc-by":
        if license_url:
            return f"Credit: {title} — {creator} | {license_url} | {source_url}"
        return f"Credit: {title} — {creator} | {source_url}"
    return f"Source: {source_url}" if source_url else ""


def choose_candidate(state):
    current = state.get("current")
    if current and current.get("candidate"):
        return current["candidate"], int(current.get("next_part") or 1), True

    completed = set(str(x) for x in state.get("completed") or [])
    terms = trend_terms()
    pool = archive_candidates(terms) + commons_candidates(terms)
    pool = [c for c in pool if c.get("key") not in completed]
    pool.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    if not pool:
        raise RuntimeError("No rights-clear source candidates were discovered.")

    errors = []
    for c in pool[:30]:
        try:
            resolved = resolve_candidate(c)
            if not resolved:
                continue
            if resolved.get("license_kind") not in ("public-domain", "cc-by"):
                continue
            return resolved, 1, False
        except Exception as e:
            errors.append(f"{c.get('key')}: {e}")
    raise RuntimeError("No candidate passed the rights and media checks. " + "; ".join(errors[-5:]))


def download(candidate):
    for p in WORK.glob("source*"):
        if p.is_file():
            p.unlink()
    url = candidate["download_url"]
    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext not in (".mp4", ".m4v", ".webm", ".mov"):
        ext = ".mp4"
    dest = (WORK / "source").with_suffix(ext)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as r, dest.open("wb") as f:
        total = 0
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DOWNLOAD_BYTES:
                raise RuntimeError("Source exceeded the configured download limit.")
            f.write(chunk)
    if not dest.exists() or dest.stat().st_size < 500_000:
        raise RuntimeError("Source download was empty or too small.")
    return dest


def probe(path):
    raw = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=index,codec_type,width,height",
        "-of", "json", str(path)
    ], capture=True)
    data = json.loads(raw)
    duration = float((data.get("format") or {}).get("duration") or 0)
    video = next((s for s in data.get("streams") or [] if s.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError("Source has no video stream.")
    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
    }


def segment_plan(duration):
    duration = float(duration)
    if duration < MIN_SOURCE_SECONDS or duration > MAX_SOURCE_SECONDS:
        raise RuntimeError(f"Source duration {duration:.1f}s is outside the accepted range.")
    if duration <= MAX_SECONDS:
        return [(0.0, duration)]
    count = max(1, math.ceil(duration / TARGET_SECONDS))
    part = duration / count
    if part > MAX_SECONDS:
        count = math.ceil(duration / MAX_SECONDS)
        part = duration / count
    return [(i * part, duration if i == count - 1 else (i + 1) * part) for i in range(count)]


def render(source, candidate, part_index, segments):
    start, end = segments[part_index - 1]
    duration = max(1.0, end - start)
    title = safe_text(candidate.get("title") or candidate.get("title_hint"), "Trending video")
    title_file = WORK / "title.txt"
    part_file = WORK / "part.txt"
    title_file.write_text(title[:90])
    part_file.write_text(f"PART {part_index} OF {len(segments)}")
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    out = OUT / f"facebook-part-{part_index:02d}-of-{len(segments):02d}.mp4"
    vf = (
        "[0:v]split=2[bg0][fg0];"
        "[bg0]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,gblur=sigma=34[bg];"
        "[fg0]scale=1040:1600:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2+80[base];"
        "[base]drawbox=x=40:y=70:w=1000:h=220:color=black@0.58:t=fill,"
        f"drawtext=fontfile={font}:textfile={title_file.as_posix()}:"
        "fontcolor=white:fontsize=42:x=(w-text_w)/2:y=105,"
        f"drawtext=fontfile={font}:textfile={part_file.as_posix()}:"
        "fontcolor=white:fontsize=46:x=(w-text_w)/2:y=215[v]"
    )
    run([
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
        "-filter_complex", vf,
        "-map", "[v]", "-map", "0:a?",
        "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", str(out),
    ])
    info = probe(out)
    if info["width"] != 1080 or info["height"] != 1920:
        raise RuntimeError("Rendered video dimensions are invalid.")
    return out, info, start, end


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    state = load_state()
    candidate, part_index, continuing = choose_candidate(state)
    source = download(candidate)
    info = probe(source)
    segments = segment_plan(info["duration"])
    if part_index < 1 or part_index > len(segments):
        part_index = 1

    video, out_info, start, end = render(source, candidate, part_index, segments)
    evidence = {
        "provider": candidate.get("provider"),
        "providerId": candidate.get("provider_id"),
        "sourceUrl": candidate.get("source_url"),
        "downloadUrl": candidate.get("download_url"),
        "creator": candidate.get("creator"),
        "licenseKind": candidate.get("license_kind"),
        "licenseUrl": candidate.get("license_url"),
        "rights": candidate.get("rights"),
        "discoveredTrend": candidate.get("trend_term") or None,
        "score": candidate.get("score"),
        "downloads": candidate.get("downloads"),
        "capturedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    manifest = {
        "pipeline": "rubysrealm-autonomous-rights-clear-facebook-v1",
        "sourceKey": candidate["key"],
        "title": safe_text(candidate.get("title") or candidate.get("title_hint"), "Trending video"),
        "part": part_index,
        "totalParts": len(segments),
        "segmentStart": round(start, 3),
        "segmentEnd": round(end, 3),
        "durationSeconds": round(out_info["duration"], 3),
        "width": out_info["width"],
        "height": out_info["height"],
        "file": video.name,
        "credit": credit_line(candidate),
        "rightsEvidence": evidence,
        "qualityPassed": True,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (OUT / "rights-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")

    if not continuing:
        state["current"] = {
            "candidate": candidate,
            "next_part": 1,
            "total_parts": len(segments),
        }
        save_state(state)

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise
