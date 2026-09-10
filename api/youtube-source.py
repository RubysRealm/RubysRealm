from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from yt_dlp import YoutubeDL
import html
import json
import re
import urllib.parse
import urllib.request

app = FastAPI()

COBALT_APIS = [
    'https://cobalt-api.meowing.de/',
    'https://capi.3kh0.net/',
]

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'


def fetch_text(url, timeout=35):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/json;q=0.9,*/*;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode('utf-8', 'replace')


def youtube_oembed(video_id):
    target = urllib.parse.quote(f'https://www.youtube.com/watch?v={video_id}', safe='')
    raw = fetch_text(f'https://www.youtube.com/oembed?url={target}&format=json', timeout=20)
    return json.loads(raw)


def inspect_page(search_url, title):
    page = fetch_text(search_url, timeout=35)
    decoded = html.unescape(page)
    links = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', decoded, flags=re.I):
        full = urllib.parse.urljoin(search_url, href)
        if full not in links:
            links.append(full)
    media = []
    for u in re.findall(r'https?://[^\s"\'<>]+', decoded, flags=re.I):
        low = u.lower()
        if any(x in low for x in ('.mp4', '.m3u8', 'videoplayback', 'googlevideo', 'download', 'embed')) and u not in media:
            media.append(u)
    marker = title.lower()[:48]
    pos = decoded.lower().find(marker)
    snippet = decoded[max(0, pos - 3000):pos + 9000] if pos >= 0 else decoded[:12000]
    return {'searchUrl': search_url, 'links': links[:200], 'media': media[:80], 'snippet': snippet}


def mirror_debug(video_id):
    meta = youtube_oembed(video_id)
    title = str(meta.get('title') or '').strip()
    if not title:
        raise RuntimeError('oEmbed title unavailable')
    out = {'title': title}
    targets = {
        'salda': 'https://salda.ws/video.php?q=' + urllib.parse.quote_plus(title),
        'clipzui': 'https://www.clipzui.cc/?q=' + urllib.parse.quote_plus(title),
    }
    for name, target in targets.items():
        try:
            out[name] = inspect_page(target, title)
        except Exception as exc:
            out[name] = {'error': f'{type(exc).__name__}: {exc}'}
    return out


def cobalt_resolve(url):
    payload = json.dumps({
        'url': url,
        'videoQuality': '720',
        'downloadMode': 'auto',
        'youtubeVideoCodec': 'h264',
        'filenameStyle': 'basic',
    }).encode('utf-8')
    errors = []
    for api in COBALT_APIS:
        try:
            req = urllib.request.Request(
                api,
                data=payload,
                method='POST',
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'User-Agent': 'rubys-realm-source/1.0 (+https://github.com/RubysRealm/RubysRealm)',
                },
            )
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode('utf-8', 'replace'))
            direct = str(data.get('url') or '').strip()
            if direct and data.get('status') in ('redirect', 'tunnel'):
                return direct, api, data.get('filename')
            errors.append(f'{api}: {data.get("status") or "no-url"}')
        except Exception as exc:
            errors.append(f'{api}: {type(exc).__name__}: {str(exc)[:220]}')
    raise RuntimeError('; '.join(errors))


@app.get('/api/youtube-source')
def youtube_source(v: str = Query(..., min_length=6, max_length=20), debug: bool = False):
    url = f'https://www.youtube.com/watch?v={v}'
    errors = []

    if debug:
        try:
            return JSONResponse({'ok': True, 'mirrors': mirror_debug(v)})
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f'mirror debug: {exc}')

    try:
        direct, api, filename = cobalt_resolve(url)
        return JSONResponse({
            'ok': True,
            'id': v,
            'directUrl': direct,
            'source': f'cobalt:{api}',
            'filename': filename,
        })
    except Exception as exc:
        errors.append(f'cobalt: {exc}')

    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'format': 'best[ext=mp4][vcodec!=none][acodec!=none]/best[vcodec!=none][acodec!=none]/best',
        'socket_timeout': 25,
        'retries': 2,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        direct = str((info or {}).get('url') or '').strip()
        if not direct:
            raise RuntimeError('No direct media URL was resolved')
        return JSONResponse({
            'ok': True,
            'id': str(info.get('id') or v),
            'title': str(info.get('title') or ''),
            'duration': info.get('duration'),
            'directUrl': direct,
            'ext': info.get('ext'),
            'formatId': info.get('format_id'),
            'source': 'yt-dlp',
        })
    except Exception as exc:
        errors.append(f'yt-dlp: {exc}')

    raise HTTPException(status_code=502, detail=' | '.join(errors)[:1800])
