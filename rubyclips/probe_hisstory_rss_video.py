#!/usr/bin/env python3
import re,urllib.request,xml.etree.ElementTree as ET,json
URL='https://anchor.fm/s/10ff75318/podcast/rss'
req=urllib.request.Request(URL,headers={'User-Agent':'Mozilla/5.0'})
xml=urllib.request.urlopen(req,timeout=60).read().decode('utf-8','replace')
target='His Mom Made Him Kneel On Broken Glass'
m=re.search(r'<item>(?:(?!</item>).)*?His Mom Made Him Kneel On Broken Glass(?:(?!</item>).)*?</item>',xml,re.I|re.S)
snippet=m.group(0) if m else ''
patterns={
 'enclosures': re.findall(r'<enclosure\b[^>]*>',snippet,re.I),
 'alternateEnclosures': re.findall(r'<(?:podcast:)?alternateEnclosure\b[^>]*>(.*?)</(?:podcast:)?alternateEnclosure>|<(?:podcast:)?alternateEnclosure\b[^>]*/>',snippet,re.I|re.S),
 'mediaContent': re.findall(r'<media:content\b[^>]*>',snippet,re.I),
 'allVideoRefs': re.findall(r'https?://[^"\'<>\s]+(?:\.mp4|video)[^"\'<>\s]*',snippet,re.I),
}
print('RSS_BYTES',len(xml))
print('ITEM_BYTES',len(snippet))
print(snippet[:12000])
print('\n---PARSED---')
print(json.dumps(patterns,indent=2))
