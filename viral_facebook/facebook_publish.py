#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GRAPH = "https://graph.facebook.com/v26.0"
BOOTSTRAP_TOKEN = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
TARGET_PAGE = os.environ.get("FACEBOOK_TARGET_PAGE", "Ruby’s Realm").strip()
TARGET_PAGE_ID = os.environ.get("FACEBOOK_TARGET_PAGE_ID", "").strip()
OUTPUT_DIR = Path("viral_facebook/output")
MANIFEST = OUTPUT_DIR / "manifest.json"
PUBLISH_RESULT = Path("/tmp/facebook-publish.json")


def norm(s):
    return str(s or "").replace("’", "'").replace("‘", "'").strip().lower()


def request_json(url, *, method="GET", token=None, form=None, body=None, headers=None):
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    data = body
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw or "{}")
        except Exception:
            payload = {"raw": raw}
        return e.code, payload


def fail(stage, code, payload):
    err = payload.get("error") if isinstance(payload, dict) else payload
    raise RuntimeError(f"{stage} failed (HTTP {code}): {err or payload}")


def select_page():
    # If the exact Page ID is already known from a previously successful managed-
    # Page lookup, avoid /me and /me/accounts entirely. Some Meta account/app
    # blocks affect identity lookup before a Page-scoped publish call is tried.
    if TARGET_PAGE_ID:
        return {
            "id": TARGET_PAGE_ID,
            "name": TARGET_PAGE or TARGET_PAGE_ID,
            "access_token": BOOTSTRAP_TOKEN,
        }

    fields = urllib.parse.quote("id,name,access_token,tasks", safe=",")
    code, data = request_json(f"{GRAPH}/me/accounts?fields={fields}", token=BOOTSTRAP_TOKEN)
    if 200 <= code < 300:
        rows = data.get("data") or []
        eligible = [p for p in rows if p.get("access_token") and "CREATE_CONTENT" in (p.get("tasks") or [])]
        exact = next((p for p in eligible if norm(p.get("name")) == norm(TARGET_PAGE)), None)
        if exact:
            return exact
        if eligible:
            names = ", ".join(str(p.get("name") or p.get("id")) for p in eligible)
            raise RuntimeError(f"Target Facebook Page {TARGET_PAGE!r} was not returned. Managed Pages: {names}")

    direct_fields = urllib.parse.quote("id,name,tasks", safe=",")
    dcode, direct = request_json(f"{GRAPH}/me?fields={direct_fields}", token=BOOTSTRAP_TOKEN)
    if dcode < 200 or dcode >= 300 or not isinstance(direct, dict) or not direct.get("id"):
        fail("Direct Page token lookup", dcode, direct)
    page_name = str(direct.get("name") or "").strip()
    if TARGET_PAGE and page_name and norm(page_name) != norm(TARGET_PAGE):
        raise RuntimeError(f"Configured Facebook token resolves to {page_name!r}, not {TARGET_PAGE!r}.")
    direct["access_token"] = BOOTSTRAP_TOKEN
    return direct


def lookup_permalink(video_id, page_token):
    fields = urllib.parse.quote("id,permalink_url", safe=",")
    for _ in range(6):
        code, data = request_json(f"{GRAPH}/{video_id}?fields={fields}", token=page_token)
        if 200 <= code < 300 and isinstance(data, dict) and data.get("id"):
            return str(data.get("permalink_url") or "").strip(), data
        time.sleep(2)
    return "", None


def main():
    if not BOOTSTRAP_TOKEN:
        raise RuntimeError("FACEBOOK_PAGE_ACCESS_TOKEN is missing.")
    if not MANIFEST.exists():
        raise RuntimeError("Facebook render manifest is missing.")

    manifest = json.loads(MANIFEST.read_text())
    video_name = str(manifest.get("file") or "").strip()
    video = OUTPUT_DIR / video_name
    if not video_name or not video.exists():
        videos = sorted(OUTPUT_DIR.glob("*.mp4"))
        if not videos:
            raise RuntimeError("Rendered Facebook video is missing.")
        video = videos[0]

    description = str(manifest.get("postDescription") or manifest.get("title") or "").strip()
    page = select_page()
    page_id = str(page["id"])
    page_name = str(page.get("name") or page_id)
    page_token = str(page["access_token"])
    print(f"Facebook Page selected: {page_name} ({page_id})")

    code, start = request_json(
        f"{GRAPH}/{page_id}/video_reels",
        method="POST",
        token=page_token,
        form={"upload_phase": "start"},
    )
    video_id = str(start.get("video_id") or "").strip() if isinstance(start, dict) else ""
    upload_url = str(start.get("upload_url") or "").strip() if isinstance(start, dict) else ""
    if code < 200 or code >= 300 or not video_id or not upload_url:
        fail("Facebook Reel start", code, start)

    size = video.stat().st_size
    upload_headers = {
        "Authorization": f"OAuth {page_token}",
        "offset": "0",
        "file_size": str(size),
        "Content-Type": "application/octet-stream",
    }
    with video.open("rb") as f:
        raw = f.read()
    code, uploaded = request_json(upload_url, method="POST", body=raw, headers=upload_headers)
    if code < 200 or code >= 300 or uploaded.get("success") is not True:
        fail("Facebook Reel binary upload", code, uploaded)

    code, finished = request_json(
        f"{GRAPH}/{page_id}/video_reels",
        method="POST",
        token=page_token,
        form={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": description,
        },
    )
    if code < 200 or code >= 300 or finished.get("success") is not True:
        fail("Facebook Reel publish", code, finished)

    permalink, graph_video = lookup_permalink(video_id, page_token)
    if not permalink:
        permalink = f"https://www.facebook.com/reel/{video_id}"

    result = {
        "id": video_id,
        "success": True,
        "pageId": page_id,
        "pageName": page_name,
        "permalink": permalink,
        "graphVideo": graph_video,
        "finish": finished,
    }
    PUBLISH_RESULT.write_text(json.dumps(result))
    print(f"Facebook accepted Reel: {video_id}")
    print(f"Facebook Reel permalink: {permalink}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise
