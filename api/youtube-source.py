from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from yt_dlp import YoutubeDL

app = FastAPI()

@app.get('/api/youtube-source')
def youtube_source(v: str = Query(..., min_length=6, max_length=20)):
    url = f'https://www.youtube.com/watch?v={v}'
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
        })
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:1200])
