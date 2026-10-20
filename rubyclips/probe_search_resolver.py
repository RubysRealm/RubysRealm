#!/usr/bin/env python3
import html,re,urllib.parse,urllib.request,json
TITLE='His Mom Made Him Kneel On Broken Glass'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode('utf-8','replace')

out={}
q=urllib.parse.quote_plus(f'"{TITLE}" His Story Facebook')
for name,url in [
    ('ddg',f'https://html.duckduckgo.com/html/?q={q}'),
    ('bing',f'https://www.bing.com/search?q={q}&count=20'),
]:
    try:
        page=get(url)
        urls=[]
        for m in re.finditer(r'https?://[^"\'<> ]+',html.unescape(page)):
            u=m.group(0).replace('&amp;','&')
            if any(d in u for d in ['facebook.com','tiktok.com','youtube.com']):
                urls.append(u)
        # Decode DDG redirect URLs.
        decoded=[]
        for u in urls:
            if 'duckduckgo.com/l/?' in u:
                qs=urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
                if qs.get('uddg'): u=qs['uddg'][0]
            u=u.split('&rut=')[0]
            if u not in decoded: decoded.append(u)
        out[name]={'bytes':len(page),'urls':decoded[:30],'sample':re.sub(r'\s+',' ',page[:800])}
    except Exception as e:
        out[name]={'error':repr(e)}
print(json.dumps(out,indent=2))
