#!/usr/bin/env python3
import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright
from yt_dlp import YoutubeDL

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / 'rubyclips'
STATE_PATH = BASE / 'facebook_state.json'
WORK = BASE / 'facebook_work'
OUT = BASE / 'facebook_output'
SOURCE_URL = 'https://www.facebook.com/share/198HW9AwHZ/?mibextid=wwXIfr'


def video_id(url):
    s = str(url or '')
    for pattern in [r'/reel/(\d+)', r'/reels/(\d+)', r'/videos/(\d+)', r'[?&]v=(\d+)']:
        m = re.search(pattern, s)
        if m:
            return m.group(1)
    return None


def normalize(url):
    if not url:
        return None
    url = str(url).replace('&amp;', '&')
    if url.startswith('/'):
        url = 'https://www.facebook.com' + url
    if not url.startswith('http') or 'facebook.com' not in urlparse(url).netloc.lower():
        return None
    p = urlparse(url)
    q = parse_qs(p.query)
    if p.path.rstrip('/') == '/watch' and q.get('v'):
        return f"https://www.facebook.com/watch/?v={q['v'][0]}"
    if p.path == '/video.php' and q.get('v'):
        return f"https://www.facebook.com/video.php?v={q['v'][0]}"
    clean = f'https://www.facebook.com{p.path}'
    return clean.rstrip('/') + '/'


async def discover_browser():
    ordered = []
    resolved = SOURCE_URL
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1500},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/129 Safari/537.36',
            locale='en-US',
        )
        page = await context.new_page()
        await page.goto(SOURCE_URL, wait_until='domcontentloaded', timeout=90000)
        await page.wait_for_timeout(4000)
        resolved = page.url

        for label in ['Allow all cookies', 'Decline optional cookies', 'Not now', 'Close']:
            try:
                b = page.get_by_role('button', name=re.compile(label, re.I)).first
                if await b.count():
                    await b.click(timeout=1200)
            except Exception:
                pass

        parsed = urlparse(resolved)
        pages = [resolved]
        if 'facebook.com' in parsed.netloc.lower() and not parsed.path.startswith('/share/'):
            base = f'https://www.facebook.com{parsed.path.rstrip("/")}'
            pages += [base + '/videos/', base + '/reels/']

        seen_pages = set()
        for target in pages:
            if target in seen_pages:
                continue
            seen_pages.add(target)
            try:
                if page.url != target:
                    await page.goto(target, wait_until='domcontentloaded', timeout=60000)
                    await page.wait_for_timeout(2500)
            except Exception:
                continue

            unchanged = 0
            prior_count = len(ordered)
            for _ in range(60):
                try:
                    hrefs = await page.locator('a[href]').evaluate_all('els => els.map(e => e.href)')
                except Exception:
                    hrefs = []
                html = await page.content()
                hrefs += re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
                for raw in hrefs:
                    u = normalize(raw)
                    vid = video_id(u)
                    if vid and all(video_id(x) != vid for x in ordered):
                        ordered.append(u)
                for vid in re.findall(r'"video_id"\s*:\s*"?(\d{8,})"?', html):
                    u = f'https://www.facebook.com/watch/?v={vid}'
                    if all(video_id(x) != vid for x in ordered):
                        ordered.append(u)

                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1100)
                if len(ordered) == prior_count:
                    unchanged += 1
                else:
                    unchanged = 0
                    prior_count = len(ordered)
                if unchanged >= 7:
                    break
        await browser.close()
    return resolved, ordered


def metadata(url):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'socket_timeout': 35,
        'retries': 2,
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError('No Facebook metadata returned')
    return {
        'id': str(info.get('id') or video_id(url) or ''),
        'url': info.get('webpage_url') or url,
        'title': str(info.get('title') or '').strip(),
        'description': str(info.get('description') or '').strip(),
        'timestamp': int(info.get('timestamp') or info.get('release_timestamp') or 0),
        'upload_date': str(info.get('upload_date') or ''),
        'duration': float(info.get('duration') or 0),
    }


def download(meta):
    template = str(WORK / 'source.%(ext)s')
    opts = {
        'format': 'bv*+ba/b',
        'merge_output_format': 'mp4',
        'outtmpl': template,
        'noplaylist': True,
        'quiet': False,
        'no_warnings': True,
        'socket_timeout': 45,
        'retries': 4,
        'fragment_retries': 4,
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([meta['url']])
    files = [f for f in WORK.glob('source.*') if f.is_file()]
    if not files:
        raise RuntimeError('Facebook download produced no file')
    return max(files, key=lambda f: f.stat().st_size)


def mp4_copy(src, dst):
    if src.suffix.lower() == '.mp4':
        shutil.copy2(src, dst)
        return
    try:
        subprocess.run([
            'ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(src),
            '-c','copy','-movflags','+faststart',str(dst)
        ], check=True, timeout=300)
    except Exception:
        subprocess.run([
            'ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(src),
            '-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p',
            '-c:a','aac','-b:a','160k','-movflags','+faststart',str(dst)
        ], check=True, timeout=1200)


def caption_for(meta):
    text = meta.get('description') or meta.get('title') or 'RubyClips'
    text = re.sub(r'\s+', ' ', text).strip()
    # Keep the existing Facebook post copy. Only add the channel tag if room remains.
    if len(text) > 2100:
        text = text[:2100].rstrip()
    if '#rubyclips' not in text.lower():
        text = (text + ' #rubyclips').strip()
    return text


async def main():
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    posted = {str(x) for x in state.get('postedVideoIds', [])}

    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    resolved, discovered = await discover_browser()
    if not discovered:
        raise RuntimeError('No public Facebook video links were discoverable from the supplied page URL.')

    metas = []
    # Facebook normally presents newest first. Preserve that order as a fallback while
    # using real timestamps whenever yt-dlp can read them.
    total = len(discovered)
    for i, url in enumerate(discovered):
        vid = video_id(url)
        if not vid or vid in posted:
            continue
        try:
            m = metadata(url)
        except Exception as exc:
            print(f'metadata failed for {url}: {exc}')
            m = {'id': vid, 'url': url, 'title': '', 'description': '', 'timestamp': 0, 'upload_date': '', 'duration': 0}
        m['_fallback_order'] = total - i
        metas.append(m)

    if not metas:
        (OUT / 'complete.json').write_text(json.dumps({'complete': True, 'resolvedPageUrl': resolved}, indent=2))
        print('No unposted Facebook videos remain.')
        return

    metas.sort(key=lambda m: (0, m['timestamp']) if m.get('timestamp') else (1, m['_fallback_order']))
    chosen = metas[0]
    if not chosen.get('timestamp'):
        # When dates are unavailable, reverse Facebook's normal newest-first display order.
        no_dates = [m for m in metas if not m.get('timestamp')]
        chosen = sorted(no_dates, key=lambda m: m['_fallback_order'])[0] if no_dates else chosen

    src = download(chosen)
    final = OUT / f"facebook-{chosen['id']}.mp4"
    mp4_copy(src, final)
    if final.stat().st_size < 100000:
        raise RuntimeError('Downloaded Facebook MP4 is unexpectedly small')

    manifest = {
        'platform': 'rubyclips-facebook-repost-v1',
        'sourceOwnership': 'user-provided-facebook-page',
        'sourceShareUrl': SOURCE_URL,
        'resolvedPageUrl': resolved,
        'sourceVideoId': chosen['id'],
        'sourceUrl': chosen['url'],
        'sourceTimestamp': chosen.get('timestamp') or None,
        'sourceUploadDate': chosen.get('upload_date') or None,
        'sourceDurationSeconds': chosen.get('duration') or None,
        'originalTitle': chosen.get('title') or '',
        'originalDescription': chosen.get('description') or '',
        'caption': caption_for(chosen),
        'file': final.name,
        'targetChannel': 'rubaradaclips',
        'passThrough': True,
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
