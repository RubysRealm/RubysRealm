#!/usr/bin/env python3
import html,re,urllib.parse,urllib.request

targets=[
  'reading your MOST honest stories and playing minecraft',
  'reading SCARY reddit stories while exploring an ancient city',
  'reading your MOST personal stories and playing minecraft',
]
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'

def extract(body):
    decoded=html.unescape(body).replace('\\u003d','=').replace('\\u0026','&')
    urls=[]
    patterns=[
      r'https?://(?:www\\.)?facebook\\.com/[^"<> ]+',
      r'https?%3A%2F%2F(?:www\\.)?facebook\\.com%2F[^&"<> ]+',
    ]
    for pat in patterns:
      for m in re.finditer(pat,decoded,re.I):
        u=urllib.parse.unquote(m.group(0))
        u=u.split('&')[0]
        u=re.sub(r'[)\\]}>.,]+$','',u)
        if u.startswith('http') and u not in urls: urls.append(u)
    return urls

for title in targets:
    q=f'site:facebook.com "{title}"'
    print('TITLE',title)
    endpoints=[
      ('ddg','https://html.duckduckgo.com/html/?'+urllib.parse.urlencode({'q':q})),
      ('bing','https://www.bing.com/search?'+urllib.parse.urlencode({'q':q,'count':'20'})),
      ('google','https://www.google.com/search?'+urllib.parse.urlencode({'q':q,'num':'20'})),
    ]
    for name,url in endpoints:
      try:
        req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
        body=urllib.request.urlopen(req,timeout=30).read().decode('utf-8','replace')
        urls=extract(body)
        print(name.upper(),'BYTES',len(body),'URLS',urls[:10])
        if not urls:
          snippets=[]
          for m in re.finditer(r'.{0,120}facebook.{0,240}',html.unescape(body),re.I|re.S):
            snippets.append(re.sub(r'\\s+',' ',m.group(0))[:360])
          print(name.upper(),'SNIPS',snippets[:4])
      except Exception as e:
        print(name.upper(),'FAIL',repr(e))
