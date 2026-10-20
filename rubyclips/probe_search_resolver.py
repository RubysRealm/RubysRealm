#!/usr/bin/env python3
import html,re,urllib.parse,urllib.request,json
from html.parser import HTMLParser

TITLE='His Mom Made Him Kneel On Broken Glass'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'

class AParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links=[]
        self._href=None
        self._text=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=='a':
            self._href=dict(attrs).get('href')
            self._text=[]
    def handle_data(self,data):
        if self._href is not None: self._text.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=='a' and self._href is not None:
            self.links.append((self._href,' '.join(self._text).strip()))
            self._href=None; self._text=[]

def get(url):
    req=urllib.request.Request(url,headers={
        'User-Agent':UA,
        'Accept-Language':'en-US,en;q=0.9',
        'Accept':'text/html,application/xhtml+xml'
    })
    with urllib.request.urlopen(req,timeout=30) as r:
        return r.read().decode('utf-8','replace')

def clean_url(href,base):
    if not href: return ''
    href=html.unescape(href)
    if href.startswith('//'): href='https:'+href
    elif href.startswith('/'): href=urllib.parse.urljoin(base,href)
    if 'duckduckgo.com/l/' in href:
        qs=urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        if qs.get('uddg'): href=qs['uddg'][0]
    # Bing sometimes wraps destination in query params
    try:
        qs=urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        for key in ('u','url','r'):
            vals=qs.get(key) or []
            for val in vals:
                dec=urllib.parse.unquote(val)
                if dec.startswith('http'): href=dec
    except: pass
    return href

queries=[
    f'"{TITLE}" His Story',
    f'"{TITLE}" Hisytstory',
    f'"{TITLE}" Facebook',
]
out={}
for query in queries:
    q=urllib.parse.quote_plus(query)
    for engine,url in [
        ('ddg',f'https://html.duckduckgo.com/html/?q={q}'),
        ('bing',f'https://www.bing.com/search?q={q}&count=30'),
    ]:
        key=f'{engine}:{query}'
        try:
            page=get(url)
            p=AParser(); p.feed(page)
            rows=[]
            for href,text in p.links:
                u=clean_url(href,url)
                if not u.startswith('http'): continue
                if any(domain in u.lower() for domain in ('facebook.com','tiktok.com','youtube.com','youtu.be')):
                    rows.append({'url':u,'text':re.sub(r'\s+',' ',text)[:300]})
            unique=[]
            seen=set()
            for row in rows:
                # strip search-tracking tail
                u=row['url'].split('&rut=')[0]
                row['url']=u
                if u not in seen:
                    seen.add(u); unique.append(row)
            out[key]={'bytes':len(page),'matches':unique[:40],
                      'anchors':len(p.links),
                      'firstAnchors':[{'href':x[0][:300],'text':re.sub(r'\s+',' ',x[1])[:180]} for x in p.links[:20]]}
        except Exception as e:
            out[key]={'error':repr(e)}
print(json.dumps(out,indent=2))
