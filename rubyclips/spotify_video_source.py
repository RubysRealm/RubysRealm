#!/usr/bin/env python3
"""Prepare verified original video and audio for the pinned Rubarata show.

Public Spotify metadata is sufficient for cataloguing, never for pretending an
audio preview or cover image is the original video. Media acquisition is either
native unencrypted Spotify media or an independently verified exact public copy.
This module never publishes or advances queue state and never stores cookies.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
from importlib.metadata import version
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

SHOW_ID = "6alyG1Jw4KH03mXZlYtPkf"
SHOW_NAME = "His Story: Animation Stories"
FIRST_EPISODE_ID = "0svGSBB9AwLrvBJTLiufbc"
TARGET_CHANNEL = "rubaradaclips"
GENERATION = 11
VOTIFY_VERSION = "1.9.9"
DEFAULT_CATALOG = Path(__file__).with_name("spotify_video_catalog.json")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
MAX_SEGMENT_SECONDS = 180
TAIL_TOLERANCE_SECONDS = 0.15
SPOTIFY_RSS = "https://anchor.fm/s/10ff75318/podcast/rss"
CREATOR_ID = "100080034373495"
CREATOR_HANDLE = "HisYTStory"
SPOTIFY_MEDIA_DOMAINS = ("anchor.fm", "spotify.com", "spotifycdn.com", "megaphone.fm", "d3ctxlq1ktw2nl.cloudfront.net")


class SourceAccessRequired(RuntimeError):
    """Source access is missing; the queue must remain on the same part."""


class SourceValidationError(RuntimeError):
    """Source identity, completeness, or output validation failed."""


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as f:
        temp = Path(f.name)
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


def require_episode_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9]{22}", value):
        raise SourceValidationError("A valid Spotify episode ID is required.")
    return value


def finite_positive(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise SourceValidationError(f"{label} is missing or invalid.") from None
    if not math.isfinite(number) or number <= 0:
        raise SourceValidationError(f"{label} is missing or invalid.")
    return number


def source_duration(episode: dict) -> float:
    return finite_positive(episode.get("durationMs"), "Spotify episode duration") / 1000


def segment_bounds(duration: float, part: int, part_seconds: int = MAX_SEGMENT_SECONDS) -> dict:
    duration = finite_positive(duration, "Source duration")
    if part_seconds != MAX_SEGMENT_SECONDS:
        raise SourceValidationError("The queue uses fixed 180-second part boundaries.")
    # A sub-frame final tail belongs to the preceding part; it is not discarded.
    total = max(1, math.ceil((duration - TAIL_TOLERANCE_SECONDS) / part_seconds))
    if isinstance(part, bool) or part < 1 or part > total:
        raise SourceValidationError("Part is outside the verified episode duration.")
    start = (part - 1) * part_seconds
    end = duration if part == total else part * part_seconds
    return {"part": part, "totalParts": total, "startSeconds": start,
            "endSeconds": round(end, 6), "sourceDurationSeconds": duration}


@contextmanager
def quiet_spotify_logs():
    # Upstream debug logging includes cookies and tokens. Disable it completely.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


async def create_api(*, authenticated: bool):
    try:
        if version("votify") != VOTIFY_VERSION:
            raise SourceValidationError(f"Install the verified client votify=={VOTIFY_VERSION}.")
        from votify.api.api import SpotifyApi
        from votify.api.enums import SessionType
    except ImportError:
        raise SourceValidationError(f"Install the verified client votify=={VOTIFY_VERSION}.") from None
    if not authenticated:
        return await SpotifyApi.create(session_type=SessionType.WEB)
    cookie_value = os.environ.get("RUBARATA_SPOTIFY_SP_DC", "").strip()
    cookie_path = os.environ.get("RUBARATA_SPOTIFY_COOKIES_FILE", "").strip()
    if cookie_value and cookie_path:
        raise SourceAccessRequired("Configure one authorized Spotify session input, not two.")
    if not cookie_value and not cookie_path:
        raise SourceAccessRequired(
            "Full Spotify video needs an authorized Spotify session or a verified matching creator transport. "
            "The public catalog and RSS audio do not provide full video."
        )
    try:
        if cookie_path:
            if not Path(cookie_path).is_file():
                raise SourceAccessRequired("The configured Spotify session file is unavailable.")
            api = await SpotifyApi.create_from_netscape_cookies(cookie_path, session_type=SessionType.WEB)
        else:
            api = await SpotifyApi.create(sp_dc=cookie_value, session_type=SessionType.WEB)
    except SourceAccessRequired:
        raise
    except Exception:
        raise SourceAccessRequired("Spotify could not authenticate the configured session; reconnect it securely.") from None
    if api.anonymous_session:
        await api.client.aclose()
        raise SourceAccessRequired("Spotify returned an anonymous session; reconnect the authorized source account.")
    return api


def episode_from_metadata(data: dict, episode_id: str, feed_index: int) -> dict:
    if data.get("uri") != f"spotify:episode:{episode_id}":
        raise SourceValidationError("Spotify returned metadata for a different episode.")
    show_uri = ((data.get("podcastV2") or {}).get("data") or {}).get("uri")
    if show_uri != f"spotify:show:{SHOW_ID}":
        raise SourceValidationError("Episode membership in the pinned Spotify show was not verified.")
    duration_data = data.get("duration") or {}
    duration_ms = duration_data.get("totalMilliseconds") if isinstance(duration_data, dict) else duration_data
    duration_ms = int(finite_positive(duration_ms, "Spotify episode duration"))
    media_types = list(data.get("mediaTypes") or [])
    title = str(data.get("name") or "").strip()
    released = str((data.get("releaseDate") or {}).get("isoString") or "")
    if not title or not released:
        raise SourceValidationError("Spotify episode title or publication date is missing.")
    return {"id": episode_id, "title": title, "releaseDate": released,
            "durationMs": duration_ms, "url": f"https://open.spotify.com/episode/{episode_id}",
            "mediaTypes": media_types, "hasVideo": "VIDEO" in media_types,
            "sourceFeedIndexNewestFirst": feed_index}


async def fetch_catalog() -> dict:
    api = None
    with quiet_spotify_logs():
        try:
            api = await create_api(authenticated=False)
            show = (await api.get_show(SHOW_ID, offset=0, limit=300))["data"]["podcastUnionV2"]
            episodes = show.get("episodesV2") or {}
            items = list(episodes.get("items") or [])
            total = int(episodes.get("totalCount") or 0)
            while len(items) < total:
                more = (await api.get_show(SHOW_ID, offset=len(items), limit=300))["data"]["podcastUnionV2"]
                page = list((more.get("episodesV2") or {}).get("items") or [])
                if not page:
                    raise SourceValidationError("Spotify catalog pagination ended before the reported total.")
                items.extend(page)
            ids = []
            for item in items:
                entity = item.get("entity") or {}
                data = entity.get("data") or {}
                uri = str(entity.get("_uri") or entity.get("uri") or data.get("uri") or "")
                if uri.startswith("spotify:episode:"):
                    ids.append(require_episode_id(uri.rsplit(":", 1)[-1]))
            if total != len(ids) or len(set(ids)) != len(ids):
                raise SourceValidationError("Spotify catalog is incomplete or contains duplicate episode IDs.")
            semaphore = asyncio.Semaphore(4)
            async def fetch_one(index: int, eid: str):
                async with semaphore:
                    data = (await api.get_episode(eid))["data"]["episodeUnionV2"]
                return episode_from_metadata(data, eid, index)
            rows = await asyncio.gather(*(fetch_one(index, eid) for index, eid in enumerate(ids)))
            rows.sort(key=lambda row: (row["releaseDate"], -row["sourceFeedIndexNewestFirst"]))
            for position, row in enumerate(rows, 1):
                row["position"] = position
            if not rows or rows[0]["id"] != FIRST_EPISODE_ID:
                raise SourceValidationError("The catalog's starting episode changed; preserve the existing queue for review.")
            return {"version": 1, "showId": SHOW_ID, "showName": SHOW_NAME,
                    "showUrl": f"https://open.spotify.com/show/{SHOW_ID}", "order": "oldest-to-newest",
                    "syncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "episodeCount": len(rows), "catalogComplete": True, "episodes": rows}
        except (SourceAccessRequired, SourceValidationError):
            raise
        except Exception:
            raise SourceValidationError("Spotify catalog could not be refreshed; the existing queue was preserved.") from None
        finally:
            if api is not None:
                await api.client.aclose()


def load_catalog(path: Path) -> dict:
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SourceValidationError("The pinned Spotify video catalog is unavailable.") from None
    rows = catalog.get("episodes") or []
    if (catalog.get("showId") != SHOW_ID or catalog.get("order") != "oldest-to-newest"
            or not catalog.get("catalogComplete") or catalog.get("episodeCount") != len(rows)
            or not rows or rows[0].get("id") != FIRST_EPISODE_ID
            or len({row.get("id") for row in rows}) != len(rows)):
        raise SourceValidationError("The Spotify catalog failed the source identity or completeness check.")
    return catalog


def catalog_episode(path: Path, episode_id: str) -> dict:
    for row in load_catalog(path)["episodes"]:
        if row["id"] == require_episode_id(episode_id):
            if row.get("hasVideo") is not True:
                raise SourceValidationError("Spotify does not list original video for this episode.")
            source_duration(row)
            return row
    raise SourceValidationError("The requested episode is not in the pinned Spotify show catalog.")


def episode_for_rss_guid(path: Path, guid: str) -> dict:
    matches = [row for row in load_catalog(path)["episodes"]
               if (row.get("rssGuid") or (row.get("verifiedTransport") or {}).get("rssGuid")) == guid]
    if len(matches) != 1:
        raise SourceValidationError("This RSS episode has not been uniquely matched to the pinned Spotify catalog.")
    return catalog_episode(path, matches[0]["id"])


def checked_url(url: str, domains: tuple[str, ...]) -> str:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.username or parsed.password or not any(
        host == domain or host.endswith("." + domain) for domain in domains
    ):
        raise SourceValidationError("The media URL is outside the verified source provider.")
    return url


def download_bytes(url: str, domains: tuple[str, ...]) -> bytes:
    checked_url(url, domains)
    class ProviderRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            checked_url(newurl, domains)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    opener = urllib.request.build_opener(ProviderRedirect())
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with opener.open(request, timeout=60) as response:
                checked_url(response.geturl(), domains)
                data = response.read()
            if len(data) < 32:
                raise SourceValidationError("Source media was empty or truncated.")
            return data
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise SourceAccessRequired("A source media download failed; the same part will be retried.") from None
            time.sleep(0.5 * (attempt + 1))
    raise SourceAccessRequired("Source download failed.")


def command(args: list[str], *, timeout: int = 1800) -> bytes:
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise SourceValidationError("The media verification or render command could not complete.") from None
    if result.returncode:
        # Do not echo subprocess command lines or signed source URLs.
        raise SourceValidationError(f"{Path(args[0]).name} failed during media verification or rendering.")
    return result.stdout


def yt_dlp_command() -> list[str]:
    args = ["yt-dlp", "--ignore-config", "--no-cache-dir"]
    # Preserve TLS verification with the runtime's explicitly configured trust
    # store. Bundled certifi otherwise ignores SSL_CERT_FILE in managed setups.
    if os.environ.get("SSL_CERT_FILE"):
        args += ["--compat-options", "no-certifi"]
    return args


def probe(path: Path) -> dict:
    info = json.loads(command(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))
    streams = info.get("streams") or []
    videos = [s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    duration = finite_positive((info.get("format") or {}).get("duration"), "Media duration")
    if len(videos) != 1 or len(audios) != 1:
        raise SourceValidationError("The media must contain one original video stream and one audio stream.")
    video, audio = videos[0], audios[0]
    if int(video.get("width") or 0) < 16 or int(video.get("height") or 0) < 16:
        raise SourceValidationError("The source has no usable original video frames.")
    vd = finite_positive(video.get("duration") or duration, "Video duration")
    ad = finite_positive(audio.get("duration") or duration, "Audio duration")
    if abs(vd - ad) > 0.3:
        raise SourceValidationError("Video and audio do not cover the same time interval.")
    return {"durationSeconds": duration, "videoDurationSeconds": vd, "audioDurationSeconds": ad,
            "videoCodec": video.get("codec_name"), "audioCodec": audio.get("codec_name"),
            "width": video["width"], "height": video["height"], "video": video, "audio": audio}


def validate_full_coverage(info: dict, expected: float) -> None:
    expected = finite_positive(expected, "Expected full episode duration")
    if min(info["videoDurationSeconds"], info["audioDurationSeconds"]) < expected - 0.20:
        raise SourceValidationError("Source media ends before the Spotify episode; previews and partial media are rejected.")
    if max(info["videoDurationSeconds"], info["audioDurationSeconds"]) > expected + 0.3:
        raise SourceValidationError("Source media duration does not match the complete Spotify episode.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def native_manifest_selection(manifest: dict, expected_duration: float) -> tuple[dict, dict, dict]:
    contents = manifest.get("contents") or []
    if len(contents) != 1:
        raise SourceValidationError("An incomplete or multi-content Spotify manifest needs source review.")
    content = contents[0]
    if content.get("encryption_infos"):
        raise SourceAccessRequired("This Spotify video is encrypted. The adapter does not decrypt media.")
    if float(content.get("start_time_millis") or 0) != 0:
        raise SourceValidationError("The Spotify manifest does not start at the beginning of the episode.")
    duration = finite_positive(content.get("end_time_millis"), "Manifest duration") / 1000
    if abs(duration - expected_duration) > 0.3:
        raise SourceValidationError("The native manifest is not the complete catalogued Spotify episode.")
    profiles = content.get("profiles") or []
    if any(any(index is not None for index in (p.get("encryption_indices") or [])) for p in profiles):
        raise SourceAccessRequired("Encrypted Spotify profiles are not supported.")
    videos = [p for p in profiles if p.get("mime_type") == "video/mp4"]
    audios = [p for p in profiles if p.get("mime_type") == "audio/mp4"]
    if not videos or not audios:
        raise SourceValidationError("Spotify did not provide both original MP4 video and audio.")
    allowed = [p for p in videos if int(p.get("video_height") or 0) <= 1080] or videos
    video = max(allowed, key=lambda p: (int(p.get("video_height") or 0), int(p.get("video_bitrate") or 0)))
    audio = max(audios, key=lambda p: int(p.get("audio_bitrate") or 0))
    return content, video, audio


def native_segment_urls(manifest: dict, content: dict, profile: dict) -> list[str]:
    bases = manifest.get("base_urls") or []
    if not bases:
        raise SourceValidationError("Spotify provided no native media address.")
    base = checked_url(str(bases[0]), ("spotifycdn.com", "spotify.com", "scdn.co"))
    initialization = str(manifest.get("initialization_template") or "")
    segments = str(manifest.get("segment_template") or "")
    segment_length = int(finite_positive(content.get("segment_length"), "Spotify segment length"))
    if not initialization or "{{segment_timestamp}}" not in segments:
        raise SourceValidationError("Spotify provided incomplete media segment templates.")
    def fill(template: str, timestamp: int = 0) -> str:
        value = template.replace("{{profile_id}}", str(profile["id"]))
        value = value.replace("{{file_type}}", str(profile["file_type"]))
        value = value.replace("{{segment_timestamp}}", str(timestamp))
        if "{{" in value:
            raise SourceValidationError("Spotify segment template contains an unknown field.")
        return checked_url(base + value, ("spotifycdn.com", "spotify.com", "scdn.co"))
    last = math.ceil(float(content["end_time_millis"]) / 1000)
    return [fill(initialization)] + [fill(segments, timestamp) for timestamp in range(0, last, segment_length)]


async def fetch_native_manifest(episode_id: str) -> dict:
    api = None
    with quiet_spotify_logs():
        try:
            api = await create_api(authenticated=True)
            response = await api.get_playback_info(episode_id, "episode", ["manifest_ids_video"])
            media = response.get("media") or {}
            item = media.get(f"spotify:episode:{episode_id}") or {}
            # Never accept a different media entry merely because it was the
            # only item in a successful response.
            item = item.get("item") or item
            if item.get("video_version_uri"):
                item = media.get(item["video_version_uri"]) or {}
            # Votify 1.9.9 returns a media envelope around the actual item.
            item = item.get("item") or item
            manifests = (item.get("manifest") or {}).get("manifest_ids_video") or []
            if not manifests or not manifests[0].get("file_id"):
                raise SourceValidationError("Spotify did not provide the requested episode's original video manifest.")
            return await api.get_video_manifest(str(manifests[0]["file_id"]))
        except (SourceAccessRequired, SourceValidationError):
            raise
        except Exception:
            raise SourceAccessRequired("Spotify refused full video access for the configured account; the part remains pending.") from None
        finally:
            if api is not None:
                await api.client.aclose()


def acquire_native(episode: dict, temp: Path) -> tuple[Path, dict]:
    manifest = asyncio.run(fetch_native_manifest(episode["id"]))
    content, video_profile, audio_profile = native_manifest_selection(manifest, source_duration(episode))
    def stream(profile: dict, path: Path) -> None:
        urls = native_segment_urls(manifest, content, profile)
        with path.open("wb") as handle, ThreadPoolExecutor(max_workers=4) as executor:
            # Bounded batches keep long episodes from occupying the whole memory.
            for start in range(0, len(urls), 12):
                for data in executor.map(lambda u: download_bytes(u, ("spotifycdn.com", "spotify.com", "scdn.co")), urls[start:start + 12]):
                    handle.write(data)
    video_file, audio_file = temp / "native-video.mp4", temp / "native-audio.mp4"
    stream(video_profile, video_file)
    stream(audio_profile, audio_file)
    full = temp / "full-source.mp4"
    command(["ffmpeg", "-y", "-v", "error", "-i", str(video_file), "-i", str(audio_file),
             "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart", str(full)])
    info = probe(full)
    validate_full_coverage(info, source_duration(episode))
    return full, {"sourceAccessMethod": "spotify-native", "sourceMedia": info,
                  "sourceSha256": sha256(full), "fullCoverage": True}


def normalized_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", html.unescape(value)).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def creator_title_matches(expected_title: str, candidate_title: str) -> bool:
    expected = normalized_title(expected_title)
    # Facebook prepends a separate "views | reactions" field to the story.
    # Match an exact title prefix after any metadata fields, never fuzzy words.
    # Joining suffix fields also preserves titles that themselves contain '|'.
    fields = candidate_title.split("|")
    return bool(expected) and any(
        normalized_title(" ".join(fields[index:])) == expected
        or normalized_title(" ".join(fields[index:])).startswith(expected + " ")
        for index in range(len(fields))
    )


def spotify_rss_items() -> list[dict]:
    try:
        root = ET.fromstring(download_bytes(SPOTIFY_RSS, SPOTIFY_MEDIA_DOMAINS))
    except ET.ParseError:
        raise SourceValidationError("Spotify's official RSS feed could not be read.") from None
    channel = root.find("channel")
    if channel is None or channel.findtext("title") != SHOW_NAME or (
        channel.findtext("link") or ""
    ).rstrip("/") != "https://podcasters.spotify.com/pod/show/hisytstory":
        raise SourceValidationError("The RSS feed does not identify the pinned Spotify show.")
    items = []
    for item in channel.findall("item"):
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "")
        except (ValueError, TypeError):
            continue
        enclosure = item.find("enclosure")
        if enclosure is None or enclosure.get("type") not in ("audio/mpeg", "audio/mp4"):
            continue
        audio_url = checked_url(str(enclosure.get("url") or ""), SPOTIFY_MEDIA_DOMAINS)
        items.append({"guid": item.findtext("guid"), "audioUrl": audio_url,
                      "title": item.findtext("title"), "releaseDate": published.isoformat()})
    return items


def match_rss_episode(episode: dict, items: list[dict]) -> dict:
    expected_date = datetime.fromisoformat(episode["releaseDate"].replace("Z", "+00:00"))
    expected_title = normalized_title(episode["title"])
    matches = [item for item in items if normalized_title(item["title"] or "") == expected_title
               and abs((datetime.fromisoformat(item["releaseDate"]) - expected_date).total_seconds()) <= 60]
    if len(matches) != 1:
        raise SourceValidationError("Exactly one matching Spotify RSS episode could not be verified.")
    if episode.get("rssGuid") and episode["rssGuid"] != matches[0]["guid"]:
        raise SourceValidationError("The Spotify episode's pinned RSS identity has changed.")
    return matches[0]


def spotify_rss_episode(episode: dict) -> dict:
    return match_rss_episode(episode, spotify_rss_items())


def spotify_preview(episode: dict) -> dict:
    url = f"https://open.spotify.com/embed/episode/{episode['id']}"
    page = download_bytes(url, ("spotify.com",)).decode("utf-8", "replace")
    match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not match:
        raise SourceAccessRequired("Spotify's original video preview is unavailable for source verification.")
    try:
        data = json.loads(match.group(1))
    except ValueError:
        raise SourceValidationError("Spotify preview metadata was invalid.") from None
    entities = []
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "episode" and value.get("id") == episode["id"]:
                entities.append(value)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(data)
    usable = [item for item in entities if item.get("hasVideo") is True and (item.get("videoPreview") or {}).get("url")]
    if not usable:
        raise SourceAccessRequired("This episode has no accessible original Spotify video preview to verify its creator transport.")
    entity = usable[0]
    if abs(finite_positive(entity.get("duration"), "Spotify preview episode duration") - episode["durationMs"]) > 300:
        raise SourceValidationError("Spotify preview metadata no longer matches the pinned episode duration.")
    return {"url": checked_url(entity["videoPreview"]["url"], ("spotifycdn.com",)), "episodeId": episode["id"]}


def _canonical_facebook_path(url: str, kinds: tuple[str, ...]) -> str | None:
    try:
        parsed = urllib.parse.urlparse(html.unescape(url))
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.hostname not in ("www.facebook.com", "facebook.com", "m.facebook.com")
                or parsed.port not in (None, 443)):
            return None
        parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) not in (3, 4) or parts[1] not in kinds or not re.fullmatch(r"[A-Za-z0-9._-]+", parts[0]):
            return None
        video_id = parts[-1]
        if not video_id.isdigit():
            return None
        handle = CREATOR_HANDLE if parts[0].casefold() in (CREATOR_HANDLE.casefold(), CREATOR_ID) else parts[0]
        return f"https://www.facebook.com/{handle}/{parts[1]}/{video_id}/"
    except ValueError:
        return None


def canonical_facebook_url(url: str) -> str | None:
    """A final, verified media URL always identifies a particular video."""
    return _canonical_facebook_path(url, ("videos",))


def canonical_facebook_candidate_url(url: str) -> str | None:
    """A public post can discover a video ID, but is not itself media proof."""
    return _canonical_facebook_path(url, ("videos", "posts"))


def canonical_creator_url(url: str) -> str | None:
    canonical = canonical_facebook_candidate_url(url)
    if canonical and urllib.parse.urlparse(canonical).path.split("/")[1] == CREATOR_HANDLE:
        return canonical
    return None


def extract_facebook_urls(page: str) -> list[str]:
    decoded = html.unescape(page).replace("\\/", "/")
    links = re.findall(r'(?:href|data-url)=["\']([^"\']+)', decoded)
    links += re.findall(r'https://(?:www\.|m\.)?facebook\.com/[^\s"\'<>]+', decoded, re.I)
    candidates = []
    for href in links:
        if href.startswith("//"):
            href = "https:" + href
        parsed = urllib.parse.urlparse(href)
        query = urllib.parse.parse_qs(parsed.query)
        if (parsed.hostname in ("duckduckgo.com", "html.duckduckgo.com") or (
                parsed.hostname is None and parsed.path.startswith("/l/"))) and query.get("uddg"):
            href = query["uddg"][0]
        elif (parsed.hostname in ("bing.com", "www.bing.com") or (
                parsed.hostname is None and parsed.path.startswith("/ck/a"))) and query.get("u"):
            wrapped = query["u"][0]
            if wrapped.startswith("a1"):
                try:
                    href = base64.urlsafe_b64decode(wrapped[2:] + "=" * (-len(wrapped[2:]) % 4)).decode("utf-8")
                except (ValueError, UnicodeError):
                    continue
            elif wrapped.startswith("https://"):
                href = wrapped
        canonical = canonical_facebook_candidate_url(href)
        if canonical and canonical not in candidates:
            candidates.append(canonical)
    return candidates


def search_transport_urls(episode: dict, *, creator_only: bool):
    title = " ".join(re.findall(r"[\w'’]+", episode["title"], flags=re.UNICODE))
    domain = "site:facebook.com/HisYTStory" if creator_only else "site:facebook.com"
    query = urllib.parse.quote_plus(f'"{title}" {domain}')
    for search_url in (
        f"https://www.bing.com/search?q={query}&count=30",
        f"https://www.bing.com/videos/search?q={query}&count=30",
        f"https://html.duckduckgo.com/html/?q={query}",
    ):
        try:
            page = download_bytes(search_url, ("bing.com", "duckduckgo.com")).decode("utf-8", "replace")
        except (SourceAccessRequired, SourceValidationError):
            continue
        for candidate in extract_facebook_urls(page):
            if not creator_only or canonical_creator_url(candidate):
                yield candidate


def discover_transport_urls(episode: dict):
    # Cached provenance is tried first and its media is fully checked again.
    # New discovery prefers the original creator. A public copy is acceptable
    # only after matching the COMPLETE Spotify soundtrack and native video frames.
    seen = set()
    prior = (episode.get("verifiedTransport") or {}).get("visualUrl")
    canonical = canonical_facebook_url(prior or "")
    if canonical:
        seen.add(canonical)
        yield canonical
    # Discovery hints have no verification flags and confer no trust. They are
    # useful when public search indexes a creator post instead of its video URL.
    hints = list(episode.get("sourceDiscoveryCandidates") or [])
    hints += [{"url": url} for url in episode.get("transportCandidates") or [] if isinstance(url, str)]
    hints = sorted(hints, key=lambda item: canonical_creator_url(str(item.get("url") or "")) is None)
    for hint in hints:
        canonical = canonical_facebook_candidate_url(str(hint.get("url") or ""))
        if canonical and canonical not in seen:
            seen.add(canonical)
            yield canonical
    for creator_only in (True, False):
        count = 0
        for candidate in search_transport_urls(episode, creator_only=creator_only):
            if candidate in seen:
                continue
            seen.add(candidate)
            yield candidate
            count += 1
            if count >= 8:
                break


def acquire_creator_video(episode: dict, url: str, temp: Path) -> tuple[Path, dict]:
    canonical = canonical_facebook_candidate_url(url)
    if not canonical:
        raise SourceValidationError("Only an exact Facebook video candidate may be verified as this episode's transport.")
    try:
        metadata = json.loads(command(yt_dlp_command() + ["--no-playlist", "--no-warnings", "--skip-download", "--dump-single-json", canonical], timeout=180))
    except (ValueError, SourceValidationError):
        raise SourceAccessRequired("The full video candidate could not be accessed for verification.") from None
    uploader_id = str(metadata.get("uploader_id") or "")
    candidate_parts = urllib.parse.urlparse(canonical).path.strip("/").split("/")
    video_id = str(metadata.get("id") or "")
    if (metadata.get("extractor") != "facebook" or not video_id.isdigit() or not uploader_id.isdigit()
            or (candidate_parts[1] == "videos" and video_id != candidate_parts[2])):
        raise SourceValidationError("The Facebook video's exact identity and uploader could not be verified.")
    prior = episode.get("verifiedTransport") or {}
    if canonical_facebook_url(prior.get("visualUrl") or "") == canonical:
        pinned_uploader = str(prior.get("uploaderId") or prior.get("creatorId") or "")
        if pinned_uploader and uploader_id != pinned_uploader:
            raise SourceValidationError("The previously verified transport's uploader identity changed.")
    for hint in episode.get("sourceDiscoveryCandidates") or []:
        if canonical_facebook_candidate_url(str(hint.get("url") or "")) == canonical:
            if hint.get("uploaderId") and str(hint["uploaderId"]) != uploader_id:
                raise SourceValidationError("The discovered video candidate's uploader identity changed.")
    if canonical_creator_url(canonical) and uploader_id != CREATOR_ID:
        raise SourceValidationError("The candidate using the creator's URL has a different uploader.")
    # /posts/ IDs identify posts, not their embedded media. Only the extractor's
    # resolved actual video ID is used for download, caching, and provenance.
    handle = CREATOR_HANDLE if uploader_id == CREATOR_ID else candidate_parts[0]
    canonical = f"https://www.facebook.com/{handle}/videos/{video_id}/"
    if not creator_title_matches(episode["title"], str(metadata.get("title") or "")):
        raise SourceValidationError("The candidate video's title does not match this Spotify episode.")
    if abs(finite_positive(metadata.get("duration"), "Full video duration") - source_duration(episode)) > 0.3:
        raise SourceValidationError("The candidate video is not the complete Spotify episode duration.")
    video = temp / f"transport-{video_id}.mp4"
    video.unlink(missing_ok=True)
    command(yt_dlp_command() + ["--no-playlist", "--no-progress", "--no-warnings", "--retries", "3", "--fragment-retries", "3",
             "-f", "bv*[height<=1080]+ba/b[height<=1080]/best", "--merge-output-format", "mp4", "--remux-video", "mp4",
             "-o", str(video), canonical], timeout=2400)
    if not video.is_file():
        raise SourceAccessRequired("The complete source video download did not finish.")
    media = probe(video)
    validate_full_coverage(media, source_duration(episode))
    method = "verified-creator-transport" if uploader_id == CREATOR_ID else "verified-public-copy"
    return video, {"visualUrl": canonical, "uploaderId": uploader_id,
                   "uploaderName": "His Story" if uploader_id == CREATOR_ID else html.unescape(str(metadata.get("uploader") or "")),
                   "sourceAccessMethod": method, "media": media}


def audio_samples(path: Path, *, start: float = 0, seconds: float | None = None, rate: int = 8000):
    import numpy as np
    args = ["ffmpeg", "-v", "error", "-ss", f"{max(0, start):.6f}", "-i", str(path), "-map", "0:a:0"]
    if seconds is not None:
        args += ["-t", f"{seconds:.6f}"]
    raw = command(args + ["-ac", "1", "-ar", str(rate), "-f", "f32le", "-"], timeout=600)
    audio = np.frombuffer(raw, dtype="<f4").copy()
    if len(audio) < rate or float(np.max(np.abs(audio))) < 0.002:
        raise SourceValidationError("Source verification requires audible original sound.")
    return audio


def best_audio_match(full, snippet, rate: int) -> tuple[float, float]:
    import numpy as np
    from scipy.signal import correlate
    if len(full) < len(snippet):
        raise SourceValidationError("The audio reference is shorter than the verification sample.")
    full = full.astype(np.float64)
    snippet = snippet.astype(np.float64)
    snippet -= snippet.mean()
    snippet_power = float(np.dot(snippet, snippet))
    if snippet_power < 1e-8:
        raise SourceValidationError("The verification audio sample contains no useful signal.")
    correlation = correlate(full, snippet, mode="valid", method="fft")
    n = len(snippet)
    sums = np.r_[0.0, np.cumsum(full)]
    powers = np.r_[0.0, np.cumsum(full * full)]
    local_sums = sums[n:] - sums[:-n]
    local_power = powers[n:] - powers[:-n] - local_sums * local_sums / n
    denominator = np.sqrt(np.maximum(local_power * snippet_power, 1e-18))
    values = correlation / denominator
    index = int(np.argmax(values))
    return index / rate, min(1.0, float(values[index]))


def verify_full_audio(creator: Path, spotify: Path, duration: float) -> dict:
    import numpy as np
    window = min(12.0, duration / 4)
    margins = 0.25
    starts = [max(margins, duration * fraction - window / 2) for fraction in (0.1, 0.5, 0.9)]
    starts = [min(start, duration - window - margins) for start in starts]
    scores, offsets = [], []
    for start in starts:
        reference = audio_samples(spotify, start=start, seconds=window)
        candidate = audio_samples(creator, start=max(0, start - margins), seconds=window + 2 * margins)
        offset, correlation = best_audio_match(candidate, reference, 8000)
        lag = offset - min(margins, start)
        if correlation < 0.95 or abs(lag) > 0.125:
            raise SourceValidationError("The creator video's sound does not match Spotify at the beginning, middle, and ending.")
        scores.append(correlation)
        offsets.append(lag)
    # Check all of the audio as well as independently aligned early/middle/late
    # windows. Matching only a few windows would miss an edited or missing span.
    reference_full = audio_samples(spotify, rate=2000)
    creator_full = audio_samples(creator, rate=2000)
    shift = int(round(float(np.median(offsets)) * 2000))
    if shift >= 0:
        creator_full = creator_full[shift:]
    else:
        reference_full = reference_full[-shift:]
    count = min(len(reference_full), len(creator_full))
    if count / 2000 < duration - 0.2 or abs(len(reference_full) - len(creator_full)) / 2000 > 0.3:
        raise SourceValidationError("The complete source audio does not cover the Spotify episode.")
    left = reference_full[:count] - reference_full[:count].mean()
    right = creator_full[:count] - creator_full[:count].mean()
    full_correlation = float(np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right)))
    if not math.isfinite(full_correlation) or full_correlation < 0.95:
        raise SourceValidationError("The full creator soundtrack differs from the Spotify episode.")
    return {"audioCorrelation": min(*scores, full_correlation), "fullAudioCorrelation": full_correlation,
            "audioWindowCorrelations": scores, "audioOffsetsSeconds": offsets,
            "audioVerifiedDurationSeconds": count / 2000}


def gray_frames(path: Path, *, start: float = 0, seconds: float | None = None):
    import numpy as np
    args = ["ffmpeg", "-v", "error", "-ss", f"{max(0, start):.6f}", "-i", str(path), "-map", "0:v:0"]
    if seconds is not None:
        args += ["-t", f"{seconds:.6f}"]
    raw = command(args + ["-vf", "fps=2,scale=48:64", "-pix_fmt", "gray", "-f", "rawvideo", "-"], timeout=600)
    frames = np.frombuffer(raw, dtype="uint8")
    if len(frames) % (48 * 64):
        raise SourceValidationError("Original video frames could not be decoded.")
    frames = frames.reshape((-1, 48 * 64)).astype(np.float32)
    if len(frames) < 4:
        raise SourceValidationError("There are too few original preview frames to verify this source.")
    frames -= frames.mean(axis=1, keepdims=True)
    norms = np.linalg.norm(frames, axis=1, keepdims=True)
    return frames / np.maximum(norms, 1e-8)


def verify_preview_frames(creator: Path, spotify_audio: Path, preview: Path, duration: float) -> dict:
    import numpy as np
    preview_info = probe(preview)
    if preview_info["durationSeconds"] >= duration + 0.3:
        raise SourceValidationError("Spotify preview is longer than the original episode.")
    rate = 2000
    original_sound = audio_samples(spotify_audio, rate=rate)
    preview_sound = audio_samples(preview, rate=rate)
    offset, audio_correlation = best_audio_match(original_sound, preview_sound, rate)
    if audio_correlation < 0.95 or offset + preview_info["durationSeconds"] > duration + 0.3:
        raise SourceValidationError("The Spotify video preview does not match the full episode's sound.")
    preview_frames = gray_frames(preview)
    # Seek to the exact audio-derived timestamp BEFORE the fps filter so both
    # sample grids have the same phase. Compare matching timestamps directly;
    # unrelated best frames from elsewhere in the video cannot satisfy this.
    original_frames = gray_frames(creator, start=offset, seconds=preview_info["durationSeconds"] + 0.1)
    if len(original_frames) < len(preview_frames):
        raise SourceValidationError("The full video is missing frames present in the Spotify preview.")
    scores = np.einsum("ij,ij->i", original_frames[:len(preview_frames)], preview_frames).tolist()
    median = float(np.median(scores))
    passing = sum(score >= 0.70 for score in scores) / len(scores)
    if median < 0.80 or passing < 0.75:
        raise SourceValidationError("The creator video's image does not match the original Spotify video preview.")
    return {"previewAudioCorrelation": audio_correlation, "previewOffsetSeconds": offset,
            "previewFrameCorrelation": median, "previewFramesPassingFraction": passing,
            "previewFramesCompared": len(scores), "previewFrameVerified": True,
            "previewFrameAlignment": "exact-spotify-audio-offset"}


def acquire_verified_creator(episode: dict, temp: Path, catalog_path: Path) -> tuple[Path, dict]:
    candidates = discover_transport_urls(episode)
    rss = spotify_rss_episode(episode)
    preview_metadata = spotify_preview(episode)
    spotify_audio = temp / "spotify-full-audio.mp3"
    spotify_audio.write_bytes(download_bytes(rss["audioUrl"], SPOTIFY_MEDIA_DOMAINS))
    preview = temp / "spotify-reference-preview.mp4"
    preview.write_bytes(download_bytes(preview_metadata["url"], ("spotifycdn.com",)))
    duration = source_duration(episode)
    last_error = None
    for candidate in candidates:
        try:
            visual, creator = acquire_creator_video(episode, candidate, temp)
            full_audio = verify_full_audio(visual, spotify_audio, duration)
            preview_match = verify_preview_frames(visual, spotify_audio, preview, duration)
            full = temp / "full-source.mp4"
            command(["ffmpeg", "-y", "-v", "error", "-i", str(visual), "-i", str(spotify_audio),
                     "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
                     "-ar", "48000", "-movflags", "+faststart", str(full)], timeout=1800)
            media = probe(full)
            validate_full_coverage(media, duration)
            verification = {"spotifyEpisodeId": episode["id"], "showId": SHOW_ID,
                            "visualUrl": creator["visualUrl"], "audioUrl": rss["audioUrl"],
                            "uploaderId": creator["uploaderId"], "uploaderName": creator["uploaderName"],
                            "sourceAccessMethod": creator["sourceAccessMethod"],
                            "rssGuid": rss["guid"], "rssFeedUrl": SPOTIFY_RSS,
                            **full_audio, **preview_match, "previewUrl": preview_metadata["url"],
                            "fullCoverage": True, "visualSha256": sha256(visual), "audioSha256": sha256(spotify_audio)}
            if creator["uploaderId"] == CREATOR_ID:
                verification["creatorId"] = CREATOR_ID
            # Cache only exact canonical provenance and measured results. All
            # media checks are repeated on future runs; a stored flag is no proof.
            catalog = load_catalog(catalog_path)
            row = next(row for row in catalog["episodes"] if row["id"] == episode["id"])
            row["verifiedTransport"] = {**verification, "verifiedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
            atomic_json(catalog_path, catalog)
            return full, {"sourceAccessMethod": creator["sourceAccessMethod"], "sourceMedia": media,
                          "sourceSha256": sha256(full), "sourceVerification": verification, "fullCoverage": True}
        except (SourceAccessRequired, SourceValidationError) as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise SourceAccessRequired("No exact full video transport could be verified for this Spotify episode; it remains queued.")


def acquire_source(episode: dict, temp: Path, catalog_path: Path) -> tuple[Path, dict]:
    if os.environ.get("RUBARATA_SPOTIFY_SP_DC") or os.environ.get("RUBARATA_SPOTIFY_COOKIES_FILE"):
        # A configured native source remains preferred. Invalid or encrypted
        # native media is a visible block, never silently replaced.
        return acquire_native(episode, temp)
    return acquire_verified_creator(episode, temp, catalog_path)


def acquire(episode_id: str, output_dir: Path, catalog_path: Path) -> dict:
    """Source-only interface for the existing generation-16 renderer/queue."""
    output_dir.mkdir(parents=True, exist_ok=True)
    source_file, info_file = output_dir / "full-source.mp4", output_dir / "source-info.json"
    info_file.unlink(missing_ok=True)
    source_file.unlink(missing_ok=True)
    episode = catalog_episode(catalog_path, episode_id)
    with tempfile.TemporaryDirectory(prefix="source-check-", dir=output_dir) as directory:
        full, evidence = acquire_source(episode, Path(directory), catalog_path)
        validate_full_coverage(evidence["sourceMedia"], source_duration(episode))
        full.replace(source_file)
    media = {key: value for key, value in evidence["sourceMedia"].items() if key not in ("video", "audio")}
    media["fullEpisode"] = True
    result = {"ok": True, "episodeId": episode_id, "title": episode["title"], "showId": SHOW_ID,
              "spotifyShowId": SHOW_ID, "sourceProvider": "spotify-video", "sourceChannel": SHOW_NAME,
              "sourceUrls": [episode["url"]], "file": str(source_file),
              "sourceDurationSeconds": source_duration(episode), "sourceMedia": media,
              "sourceVideoVerified": True, "sourceAudioVerified": True,
              "fullEpisodeVerified": True, "full_episode_verified": True,
              "sourceAccessMethod": evidence["sourceAccessMethod"], "sourceSha256": evidence["sourceSha256"]}
    if evidence.get("sourceVerification"):
        result["sourceVerification"] = evidence["sourceVerification"]
        result["rssGuid"] = evidence["sourceVerification"]["rssGuid"]
        result["transportUrl"] = evidence["sourceVerification"]["visualUrl"]
    else:
        result["rssGuid"] = episode.get("rssGuid")
    atomic_json(info_file, result)
    return result


def prepare(episode_id: str, part: int, part_seconds: int, output_dir: Path, catalog_path: Path) -> dict:
    episode = catalog_episode(catalog_path, episode_id)
    bounds = segment_bounds(source_duration(episode), part, part_seconds)
    output_dir.mkdir(parents=True, exist_ok=True)
    # A failed preparation must never leave yesterday's publishable manifest.
    for name in ("manifest.json", "part-info.json"):
        (output_dir / name).unlink(missing_ok=True)
    filename = f"spotify-{episode_id}-r{GENERATION}-part-{part:02d}.mp4"
    final = output_dir / filename
    final.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="spotify-source-", dir=output_dir) as directory:
        full, evidence = acquire_source(episode, Path(directory), catalog_path)
        source_info = evidence["sourceMedia"]
        validate_full_coverage(source_info, bounds["sourceDurationSeconds"])
        seconds = bounds["endSeconds"] - bounds["startSeconds"]
        # Scale to fit and pad, preserving the entire source image. No cover,
        # replacement footage, crop, looping still, synthetic wave, or intro.
        video_filter = "scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
        command(["ffmpeg", "-y", "-v", "error", "-i", str(full),
                 "-ss", f"{bounds['startSeconds']:.6f}", "-t", f"{seconds:.6f}",
                 "-map", "0:v:0", "-map", "0:a:0", "-vf", video_filter,
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(final)], timeout=3600)
        output = probe(final)
        validate_full_coverage(output, seconds)
        if output["durationSeconds"] > MAX_SEGMENT_SECONDS + 0.3:
            raise SourceValidationError("The rendered part exceeds its maximum duration.")
        if output["videoCodec"] != "h264" or output["audioCodec"] != "aac":
            raise SourceValidationError("The rendered part has incompatible media codecs.")
        # Decode both complete output streams to catch corrupted source segments.
        command(["ffmpeg", "-v", "error", "-xerror", "-i", str(final), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], timeout=3600)
    logical_key = f"rubyclips:{episode_id}:r{GENERATION}:p{part}"
    release_tag = f"rubyclips-tt-{episode_id}-r{GENERATION}-p{part}"
    source_media = {k: source_info[k] for k in ("videoCodec", "audioCodec", "durationSeconds", "videoDurationSeconds", "audioDurationSeconds", "width", "height")}
    source_media["fullEpisode"] = True
    manifest = {
        "platform": "rubarata-spotify-video-v1", "pipelineRevision": "original-verified-video-v1",
        "sourceProvider": "spotify-video", "showId": SHOW_ID, "spotifyShowId": SHOW_ID,
        "sourceChannel": SHOW_NAME, "sourceSeriesId": episode_id, "sourceEpisodeId": episode_id,
        "sourceSeriesTitle": episode["title"], "sourceVideoIds": [episode_id],
        "sourceUrls": [episode["url"]], "targetChannel": TARGET_CHANNEL,
        "restartGeneration": GENERATION, "logicalPostKey": logical_key, "releaseTag": release_tag,
        "segmentIndex": part, "segmentTotal": bounds["totalParts"],
        "segmentStartSeconds": bounds["startSeconds"], "segmentEndSeconds": bounds["endSeconds"],
        "sourceDurationSeconds": bounds["sourceDurationSeconds"],
        "segmentDurationSeconds": round(output["durationSeconds"], 6), "file": filename,
        "caption": f"{episode['title']} — Part {part} of {bounds['totalParts']} #HisStory #rubaradaclips",
        "sourceVideoVerified": True, "sourceAudioVerified": True,
        "fullEpisodeVerified": True, "full_episode_verified": True,
        "sourceMedia": source_media, "sourceAccessMethod": evidence["sourceAccessMethod"],
        "sourceSha256": evidence["sourceSha256"], "outputSha256": sha256(final),
        "outputVideoCodec": "h264", "outputAudioCodec": "aac",
        "mediaVideo": {"codec": "h264", "codec_name": "h264", "width": output["width"], "height": output["height"], "durationSeconds": output["videoDurationSeconds"]},
        "mediaAudio": {"codec": "aac", "codec_name": "aac", "durationSeconds": output["audioDurationSeconds"]},
        "visualMode": "original-source-video", "sourceFrameMode": "entire-image-letterbox",
        "titleBurnedIn": False, "partLabelBurnedIn": False,
        "thumbnailOffsetMs": min(1000, int(output["durationSeconds"] * 1000 / 2)),
    }
    if "sourceVerification" in evidence:
        manifest["sourceVerification"] = evidence["sourceVerification"]
    part_info = {**bounds, "episodeId": episode_id, "title": episode["title"], "file": filename,
                 "duration": round(output["durationSeconds"], 6), "logicalPostKey": logical_key,
                 "releaseTag": release_tag, "full_episode_verified": True}
    atomic_json(output_dir / "part-info.json", part_info)
    atomic_json(output_dir / "manifest.json", manifest)
    return {"ok": True, "manifest": str(output_dir / "manifest.json"), "partInfo": part_info,
            "file": str(final), "bytes": final.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    refresh = commands.add_parser("refresh-catalog")
    refresh.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    acquire_parser = commands.add_parser("acquire")
    identity = acquire_parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--episode-id")
    identity.add_argument("--rss-guid")
    acquire_parser.add_argument("--output-dir", type=Path, required=True)
    acquire_parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--episode-id", required=True)
    prepare_parser.add_argument("--part", type=int, required=True)
    prepare_parser.add_argument("--part-seconds", type=int, default=MAX_SEGMENT_SECONDS)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    args = parser.parse_args()
    try:
        if args.command == "refresh-catalog":
            catalog = asyncio.run(fetch_catalog())
            rss_items = spotify_rss_items()
            if args.catalog.exists():
                existing = load_catalog(args.catalog)
                verified = {row["id"]: row.get("verifiedTransport") for row in existing["episodes"]}
                candidates = {row["id"]: row.get("sourceDiscoveryCandidates") for row in existing["episodes"]}
                transport_candidates = {row["id"]: row.get("transportCandidates") for row in existing["episodes"]}
                rss_guids = {row["id"]: row.get("rssGuid") for row in existing["episodes"]}
                for row in catalog["episodes"]:
                    if verified.get(row["id"]):
                        row["verifiedTransport"] = verified[row["id"]]
                    if candidates.get(row["id"]):
                        row["sourceDiscoveryCandidates"] = candidates[row["id"]]
                    if transport_candidates.get(row["id"]):
                        row["transportCandidates"] = transport_candidates[row["id"]]
                    if rss_guids.get(row["id"]):
                        row["rssGuid"] = rss_guids[row["id"]]
            for row in catalog["episodes"]:
                row["rssGuid"] = match_rss_episode(row, rss_items)["guid"]
            catalog["rssFeedUrl"] = SPOTIFY_RSS
            atomic_json(args.catalog, catalog)
            result = {"ok": True, "episodeCount": catalog["episodeCount"], "catalog": str(args.catalog)}
        elif args.command == "acquire":
            episode_id = args.episode_id or episode_for_rss_guid(args.catalog, args.rss_guid)["id"]
            result = acquire(episode_id, args.output_dir, args.catalog)
        else:
            result = prepare(args.episode_id, args.part, args.part_seconds, args.output_dir, args.catalog)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except SourceAccessRequired as exc:
        print(json.dumps({"ok": False, "code": "source_access_required", "error": str(exc)}), file=sys.stderr)
        return 3
    except SourceValidationError as exc:
        print(json.dumps({"ok": False, "code": "source_validation_failed", "error": str(exc)}), file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps({"ok": False, "code": "source_preparation_failed", "error": "Source preparation failed; no part was published or advanced."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
