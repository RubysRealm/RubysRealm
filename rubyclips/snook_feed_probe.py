#!/usr/bin/env python3
"""Read the public Snook podcast feed and validate the user's starting episode."""
import json,re,urllib.request,xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

FEED="https://feeds.megaphone.fm/QCD5686868811"
TITLE="10 Unspeakable TRUE Scary Stories"
def n(s): return re.sub(r'[^a-z0-9]+',' ',str(s or '').lower()).strip()
def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; RubarataRSS/1.0)','Accept':'application/rss+xml,application/xml,*/*'})
    with urllib.request.urlopen(req,timeout=75) as r:
        return r.read()
root=ET.fromstring(fetch(FEED))
items=[]
for e in root.findall('./channel/item'):
    title=e.findtext('title') or ''
    rawdate=e.findtext('pubDate') or ''
    pubdate=parsedate_to_datetime(rawdate).isoformat() if rawdate else ''
    enclosure=e.find('enclosure')
    url=enclosure.attrib.get('url','') if enclosure is not None else ''
    mime=enclosure.attrib.get('type','') if enclosure is not None else ''
    guid=e.findtext('guid') or ''
    dur=e.findtext('{http://www.itunes.com/dtds/podcast-1.0.dtd}duration') or ''
    items.append(dict(title=title,guid=guid,date=pubdate,url=url,type=mime,duration=dur))
items.sort(key=lambda x:(x['date'],x['guid']))
matches=[(i+1,x) for i,x in enumerate(items) if n(x['title'])==n(TITLE)]
if not matches: raise SystemExit('Linked Spotify episode title absent from RSS')
i,chosen=matches[0]
if not chosen['url']: raise SystemExit('RSS start has no enclosure')
req=urllib.request.Request(chosen['url'],headers={'User-Agent':'Mozilla/5.0','Range':'bytes=0-1023'})
with urllib.request.urlopen(req,timeout=75) as resp:
    resp.read(1024)
    reach={'http':resp.status,'type':resp.headers.get('Content-Type'),'length':resp.headers.get('Content-Length')}
result={'show':'Snook','feed':FEED,'total':len(items),'startPosition':i,'start':chosen,'oldest':items[0], 'newest':items[-1],'enclosureProbe':reach,'mimeTypes':sorted(set(x['type'] for x in items))}
print(json.dumps(result,indent=2))
