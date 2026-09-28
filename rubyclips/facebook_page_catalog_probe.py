#!/usr/bin/env python3
import json, re, subprocess
from pathlib import Path

PAGE='https://www.facebook.com/100092703608304/videos/'
TARGETS=[
  'reading your MOST honest stories and playing minecraft',
  'reading SCARY reddit stories while exploring an ancient city',
  'reading your MOST personal stories and playing minecraft',
]

def norm(s):
    return re.sub(r'[^a-z0-9]+',' ',str(s or '').lower()).strip()

cmd=['yt-dlp','--flat-playlist','--playlist-end','120','--dump-json','--no-warnings','--socket-timeout','30','--retries','3',PAGE]
p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
rows=[]
for line in p.stdout.splitlines():
    line=line.strip()
    if line.startswith('{'):
        try: rows.append(json.loads(line))
        except: pass
print('COUNT',len(rows))
for row in rows[:120]:
    print(json.dumps({'id':row.get('id'),'title':row.get('title'),'url':row.get('webpage_url') or row.get('url')},ensure_ascii=False))
for target in TARGETS:
    nt=norm(target)
    exact=[r for r in rows if norm(r.get('title'))==nt]
    print('TARGET',target,'EXACT',len(exact),[(r.get('id'),r.get('title')) for r in exact[:5]])
if not rows:
    raise SystemExit(p.stdout[-3000:])
