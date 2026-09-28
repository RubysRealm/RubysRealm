#!/usr/bin/env python3
import html,re,urllib.parse,urllib.request

titles=[
  'reading SCARY reddit stories while exploring an ancient city',
  'reading your MOST personal stories and playing minecraft',
]
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'

def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    return urllib.request.urlopen(req,timeout=30).read().decode('utf-8','replace')

def urls_from(body):
    body=html.unescape(body).replace('\\u0026','&').replace('\\u003d','=')
    out=[]
    for pat in [
        r'https?://(?:www\\.)?facebook\\.com/[^"<> ]+',
        r'https?://(?:www\\.)?dailymotion\\.com/video/[A-Za-z0-9_-]+',
        r'https?://(?:www\\.)?bing\\.com/ck/a\\?[^"<> ]+',
        r'https?://duckduckgo\\.com/l/\\?[^"<> ]+',
    ]:
        for m in re.finditer(pat,body,re.I):
            u=m.group(0)
            if 'bing.com/ck/a?' in u:
                continue
            if 'duckduckgo.com/l/?' in u:
                q=urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)
                u=urllib.parse.unquote((q.get('uddg') or [''])[0])
            u=u.replace('&amp;','&')
            u=re.sub(r'[)\\]}>.,]+$','',u)
            if u and u not in out: out.append(u)
    return out

for title in titles:
    print('TITLE',title)
    queries=[
      f'"{title}" facebook',
      f'"{title}" dailymotion',
      f'"{title}" babyjamie1',
    ]
    for q in queries:
        for engine,url in [
          ('ddg','https://html.duckduckgo.com/html/?'+urllib.parse.urlencode({'q':q})),
          ('bing','https://www.bing.com/search?'+urllib.parse.urlencode({'q':q,'count':'20'})),
        ]:
            try:
                body=fetch(url)
                found=urls_from(body)
                print(engine,q,'FOUND',found[:10])
            except Exception as exc:
                print(engine,q,'ERR',repr(exc))
