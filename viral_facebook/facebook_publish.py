#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GRAPH = "https://graph.facebook.com/v26.0"
BOOTSTRAP_TOKEN = os.environ.get("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
TARGET_PAGE = os.environ.get("FACEBOOK_TARGET_PAGE", "Ruby’s Realm").strip()
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
    fields = urllib.parse.quote("id,name,access_token,tasks", safe=",")
    code, data = request_json(f"{GRAPH}/me/accounts?fields={fields}", token=BOOTSTRAP_TOKEN)
    if code < 200 or code >= 300:
        fail("Managed Page lookup", code, data)
    rows = data.get("data") or []
    eligible = [p for p in rows if p.get("access_token") and "CREATE_CONTENT" in (p.get("tasks") or [])]
    if not eligible:
        raise RuntimeError("No managed Facebook Page with CREATE_CONTENT access was returned by Meta.")
    exact = next((p for p in eligible if norm(p.get("name")) == norm(TARGET_PAGE)), None)
    return exact or eligible[0]


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

    result = {
        "id": video_id,
        "success": True,
        "pageId": page_id,
        "pageName": page_name,
        "finish": finished,
    }
    PUBLISH_RESULT.write_text(json.dumps(result))
    print(f"Facebook accepted Reel: {video_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise
