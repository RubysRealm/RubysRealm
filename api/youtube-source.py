from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from yt_dlp import YoutubeDL
import json
import urllib.request
import urllib.error

app = FastAPI()

COBALT_APIS = [
    'https://cobalt-api.meowing.de/',
    'https://capi.3kh0.net/',
]


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
def youtube_source(v: str = Query(..., min_length=6, max_length=20)):
    url = f'https://www.youtube.com/watch?v={v}'
    errors = []

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
