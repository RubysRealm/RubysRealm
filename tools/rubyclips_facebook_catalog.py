#!/usr/bin/env python3
import asyncio
import json
import re
from urllib.parse import parse_qs, urlparse

from playwright.async_api import async_playwright
from yt_dlp import YoutubeDL

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
    return f'https://www.facebook.com{p.path}'.rstrip('/') + '/'


async def discover():
    ordered = []
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
        parsed = urlparse(resolved)
        targets = [resolved]
        if 'facebook.com' in parsed.netloc.lower() and not parsed.path.startswith('/share/'):
            base = f'https://www.facebook.com{parsed.path.rstrip("/")}'
            targets += [base + '/videos/', base + '/reels/']
        for target in dict.fromkeys(targets):
            try:
                await page.goto(target, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_timeout(2500)
            except Exception:
                continue
            stagnant = 0
            old_count = len(ordered)
            for _ in range(45):
                try:
                    hrefs = await page.locator('a[href]').evaluate_all('els => els.map(e => e.href)')
                except Exception:
                    hrefs = []
                html = await page.content()
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
                await page.wait_for_timeout(900)
                if len(ordered) == old_count:
                    stagnant += 1
                else:
                    stagnant = 0
                    old_count = len(ordered)
                if stagnant >= 6:
                    break
        await browser.close()
    return resolved, ordered


def get_meta(url):
    with YoutubeDL({'quiet': True, 'no_warnings': True, 'skip_download': True, 'noplaylist': True, 'socket_timeout': 25, 'retries': 1}) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        'id': str(info.get('id') or video_id(url) or ''),
        'url': info.get('webpage_url') or url,
        'title': str(info.get('title') or '').strip(),
        'description': str(info.get('description') or '').strip()[:500],
        'timestamp': int(info.get('timestamp') or info.get('release_timestamp') or 0),
        'upload_date': str(info.get('upload_date') or ''),
        'duration': float(info.get('duration') or 0),
    }


async def main():
    resolved, urls = await discover()
    rows = []
    total = len(urls)
    for i, url in enumerate(urls):
        try:
            m = get_meta(url)
        except Exception as e:
            m = {'id': video_id(url), 'url': url, 'title': '', 'description': '', 'timestamp': 0, 'upload_date': '', 'duration': 0, 'error': str(e)}
        m['_surface_index'] = i
        m['_fallback_oldest_order'] = total - i
        rows.append(m)
    rows.sort(key=lambda m: (0, m['timestamp']) if m.get('timestamp') else (1, m['_fallback_oldest_order']))
    result = {'resolvedPageUrl': resolved, 'count': len(rows), 'oldestToNewest': rows}
    print('RUBYCLIPS_CATALOG_BEGIN')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print('RUBYCLIPS_CATALOG_END')


if __name__ == '__main__':
    asyncio.run(main())
