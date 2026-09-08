#!/usr/bin/env python3
import asyncio
import json
import math
import re
import shutil
import subprocess
import textwrap
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
MAX_TIKTOK_SECONDS = 585.0
FONT_FILE = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


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


def probe_duration(path):
    p = subprocess.run([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=nw=1:nk=1', str(path)
    ], check=True, capture_output=True, text=True)
    return float(p.stdout.strip())


def clean_title(meta):
    raw_title = re.sub(r'\s+', ' ', str(meta.get('title') or '')).strip()
    raw_desc = re.sub(r'\s+', ' ', str(meta.get('description') or '')).strip()

    # yt-dlp Facebook titles often append the Page name. Prefer the actual video title.
    candidates = []
    if raw_title:
        for separator in [' | ', ' • ', ' - ']:
            if separator in raw_title:
                pieces = [p.strip() for p in raw_title.split(separator) if p.strip()]
                candidates.extend(pieces)
                break
        else:
            candidates.append(raw_title)
    if raw_desc:
        first = re.split(r'[\n\r]|(?<=[.!?])\s+', raw_desc)[0].strip()
        if first:
            candidates.append(first)

    bad = {'facebook', 'polissya bushcraft', 'rubyclips'}
    title = next((c for c in candidates if c.lower().strip() not in bad and len(c.strip()) >= 4), 'RubyClips')
    title = re.sub(r'#[A-Za-z0-9_]+', '', title).strip(' -–—|')
    if len(title) > 76:
        title = title[:73].rstrip(' ,.;:-') + '…'
    lines = textwrap.wrap(title, width=31, break_long_words=False, break_on_hyphens=False)
    return '\n'.join(lines[:2]) if lines else 'RubyClips'


def part_label(index, total):
    return f'Part {index}/{total}' if total > 1 else 'Part 1'


def burn_layout(src, dst, title, part, start=0.0, length=None):
    title_file = WORK / 'overlay-title.txt'
    part_file = WORK / 'overlay-part.txt'
    title_file.write_text(title, encoding='utf-8')
    part_file.write_text(part, encoding='utf-8')

    def esc(path):
        return path.as_posix().replace(':', '\\:').replace("'", "\\'")

    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error']
    if start > 0:
        cmd += ['-ss', f'{start:.3f}']
    cmd += ['-i', str(src)]
    if length is not None:
        cmd += ['-t', f'{length:.3f}']

    # Requested layout: smaller title at the former Part position; Part beneath the
    # visible video area at a comparable distance. Preserve the source image itself.
    vf = (
        'scale=1080:1920:force_original_aspect_ratio=decrease,'
        'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,'
        f"drawtext=fontfile={FONT_FILE}:textfile='{esc(title_file)}':"
        "fontcolor=white:fontsize=34:line_spacing=5:"
        "box=1:boxcolor=black@0.62:boxborderw=12:"
        "x=(w-text_w)/2:y=h*0.155,"
        f"drawtext=fontfile={FONT_FILE}:textfile='{esc(part_file)}':"
        "fontcolor=white:fontsize=31:"
        "box=1:boxcolor=black@0.62:boxborderw=11:"
        "x=(w-text_w)/2:y=h*0.835"
    )
    cmd += [
        '-vf', vf,
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '19', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', str(dst)
    ]
    subprocess.run(cmd, check=True, timeout=2400)


def caption_for(meta, index, total):
    text = re.sub(r'\s+', ' ', str(meta.get('description') or meta.get('title') or 'RubyClips')).strip()
    text = f'{text} — {part_label(index, total)}'
    if len(text) > 2100:
        text = text[:2100].rstrip()
    if '#rubyclips' not in text.lower():
        text = (text + ' #rubyclips').strip()
    return text


async def main():
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    posted = {str(x) for x in state.get('postedVideoIds', [])}
    progress = {str(k): int(v) for k, v in (state.get('segmentProgress') or {}).items()}

    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    resolved, discovered = await discover_browser()
    if not discovered:
        raise RuntimeError('No public Facebook video links were discoverable from the supplied page URL.')

    metas = []
    total_found = len(discovered)
    for i, url in enumerate(discovered):
        vid = video_id(url)
        if not vid or vid in posted:
            continue
        try:
            m = metadata(url)
        except Exception as exc:
            print(f'metadata failed for {url}: {exc}')
            m = {'id': vid, 'url': url, 'title': '', 'description': '', 'timestamp': 0, 'upload_date': '', 'duration': 0}
        m['_fallback_order'] = total_found - i
        metas.append(m)

    if not metas:
        (OUT / 'complete.json').write_text(json.dumps({'complete': True, 'resolvedPageUrl': resolved}, indent=2))
        print('No unposted Facebook videos remain.')
        return

    # Oldest source video first; if timestamps are absent, reverse Facebook's usual newest-first surface order.
    metas.sort(key=lambda m: (0, m['timestamp']) if m.get('timestamp') else (1, m['_fallback_order']))
    chosen = metas[0]

    src = download(chosen)
    actual_duration = probe_duration(src)
    if actual_duration <= 0:
        raise RuntimeError('Facebook source duration is invalid')

    segment_total = max(1, int(math.ceil(actual_duration / MAX_TIKTOK_SECONDS)))
    segment_index = max(1, progress.get(str(chosen['id']), 1))
    if segment_index > segment_total:
        segment_index = 1

    start = (segment_index - 1) * MAX_TIKTOK_SECONDS
    remaining = max(0.1, actual_duration - start)
    length = min(MAX_TIKTOK_SECONDS, remaining)
    title = clean_title(chosen)
    part = part_label(segment_index, segment_total)

    if segment_total == 1:
        final = OUT / f"facebook-{chosen['id']}.mp4"
    else:
        final = OUT / f"facebook-{chosen['id']}-segment-{segment_index:02d}-of-{segment_total:02d}.mp4"
    burn_layout(src, final, title, part, start=start, length=length)

    produced_duration = probe_duration(final)
    if produced_duration > 599.0:
        raise RuntimeError(f'Produced TikTok segment is too long: {produced_duration:.2f}s')
    if final.stat().st_size < 100000:
        raise RuntimeError('Produced Facebook MP4 is unexpectedly small')

    manifest = {
        'platform': 'rubyclips-facebook-repost-v1',
        'sourceOwnership': 'user-provided-facebook-page',
        'sourceShareUrl': SOURCE_URL,
        'resolvedPageUrl': resolved,
        'sourceVideoId': chosen['id'],
        'sourceUrl': chosen['url'],
        'sourceTimestamp': chosen.get('timestamp') or None,
        'sourceUploadDate': chosen.get('upload_date') or None,
        'sourceDurationSeconds': round(actual_duration, 3),
        'segmentIndex': segment_index,
        'segmentTotal': segment_total,
        'segmentStartSeconds': round(start, 3),
        'segmentDurationSeconds': round(produced_duration, 3),
        'originalTitle': chosen.get('title') or '',
        'originalDescription': chosen.get('description') or '',
        'displayTitle': title.replace('\n', ' '),
        'partLabel': part,
        'caption': caption_for(chosen, segment_index, segment_total),
        'file': final.name,
        'targetChannel': 'rubaradaclips',
        'technicalSplitOnly': segment_total > 1,
        'titleBurnedIn': True,
        'partLabelBurnedIn': True,
        'overlayLayoutVersion': 'title-midtop-part-lower-v2'
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
