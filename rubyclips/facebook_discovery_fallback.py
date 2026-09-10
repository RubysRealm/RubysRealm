#!/usr/bin/env python3
import asyncio
import importlib.util
import re
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('rubyclips_facebook_pipeline', HERE / 'facebook_pipeline.py')
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)

PAGE_ID = '61577485822570'


def add_candidate(ordered, raw):
    raw = str(raw or '').replace('\\/', '/').replace('&amp;', '&')
    url = pipeline.normalize(raw)
    vid = pipeline.video_id(url)
    if vid and all(pipeline.video_id(existing) != vid for existing in ordered):
        ordered.append(url)


async def discover_browser_fallback():
    ordered = []
    resolved = 'https://www.facebook.com/people/Polissya-Bushcraft/61577485822570/'
    targets = [
        pipeline.SOURCE_URL,
        resolved,
        f'https://www.facebook.com/{PAGE_ID}/videos/',
        f'https://www.facebook.com/{PAGE_ID}/reels/',
        f'https://www.facebook.com/profile.php?id={PAGE_ID}&sk=videos',
        f'https://m.facebook.com/profile.php?id={PAGE_ID}&sk=videos',
    ]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 1800},
            user_agent='Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 Chrome/151 Mobile Safari/537.36',
            locale='en-US',
        )
        page = await context.new_page()

        for target in targets:
            try:
                await page.goto(target, wait_until='domcontentloaded', timeout=75000)
                await page.wait_for_timeout(3500)
                if '/share/' not in page.url:
                    resolved = page.url
            except Exception as exc:
                print(f'fallback route failed: {target}: {exc}')
                continue

            for label in ['Allow all cookies', 'Decline optional cookies', 'Not now', 'Close']:
                try:
                    button = page.get_by_role('button', name=re.compile(label, re.I)).first
                    if await button.count():
                        await button.click(timeout=1200)
                except Exception:
                    pass

            unchanged = 0
            last_count = len(ordered)
            for _ in range(80):
                try:
                    hrefs = await page.locator('a[href]').evaluate_all('els => els.map(e => e.href)')
                except Exception:
                    hrefs = []
                for href in hrefs:
                    add_candidate(ordered, href)

                try:
                    html = await page.content()
                except Exception:
                    html = ''

                # Explicit Facebook video/reel URL forms, including JSON-escaped URLs.
                for raw in re.findall(r'https?:\\?/\\?/(?:www\\.|m\\.)?facebook\\.com[^"\'<> ]+(?:videos|reel|reels)[^"\'<> ]*', html, re.I):
                    add_candidate(ordered, raw)
                for raw in re.findall(r'(?:href|url)=["\']([^"\']+)["\']', html, re.I):
                    add_candidate(ordered, raw)

                # Relay/GraphQL payload keys used by Facebook for video objects.
                for pattern in [
                    r'"video_id"\s*:\s*"?(\d{8,})"?',
                    r'"videoId"\s*:\s*"?(\d{8,})"?',
                    r'"videoID"\s*:\s*"?(\d{8,})"?',
                ]:
                    for vid in re.findall(pattern, html):
                        add_candidate(ordered, f'https://www.facebook.com/watch/?v={vid}')

                try:
                    await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    await page.wait_for_timeout(1200)
                except Exception:
                    break

                if len(ordered) == last_count:
                    unchanged += 1
                else:
                    unchanged = 0
                    last_count = len(ordered)
                if unchanged >= 9:
                    break

            print(f'fallback route {target} discovered {len(ordered)} unique video ids total')

        await browser.close()

    print('fallback discovered ids:', [pipeline.video_id(x) for x in ordered])
    return resolved, ordered


pipeline.discover_browser = discover_browser_fallback
asyncio.run(pipeline.main())
