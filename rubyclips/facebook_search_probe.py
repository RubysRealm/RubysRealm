#!/usr/bin/env python3
import html,re,urllib.parse,urllib.request

targets=[
  'reading your MOST honest stories and playing minecraft',
  'reading SCARY reddit stories while exploring an ancient city',
  'reading your MOST personal stories and playing minecraft',
]
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'
for title in targets:
    q=f'site:facebook.com "{title}"'
    url='https://www.google.com/search?'+urllib.parse.urlencode({'q':q,'num':'10'})
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    try:
        body=urllib.request.urlopen(req,timeout=30).read().decode('utf-8','replace')
    except Exception as e:
        print('GOOGLE_FAIL',title,repr(e))
        body=''
    urls=[]
    for m in re.finditer(r'https?://(?:www\.)?facebook\.com/[^&"<> ]+',html.unescape(body)):
        u=m.group(0)
        u=re.sub(r'[)\]}>.,]+$','',u)
        if u not in urls: urls.append(u)
    print('TITLE',title)
    print('URLS',urls[:10])
    print('BYTES',len(body))
