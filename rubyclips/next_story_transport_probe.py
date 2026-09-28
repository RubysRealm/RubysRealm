#!/usr/bin/env python3
import json, subprocess
title='reading SCARY reddit stories while exploring an ancient city'
query=f'ytsearch5:{title} babyjamie1'
cmd=[
  'yt-dlp','--skip-download','--dump-json','--no-warnings',
  '--socket-timeout','25','--retries','3',
  '--js-runtimes','node','--remote-components','ejs:github',query
]
p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
rows=[]
for line in p.stdout.splitlines():
    if line.strip().startswith('{'):
        try: rows.append(json.loads(line))
        except: pass
if not rows:
    raise SystemExit(p.stdout[-3000:])
best=rows[0]
vid=str(best.get('id') or '')
url=str(best.get('webpage_url') or f'https://www.youtube.com/watch?v={vid}')
print('MATCH',vid,best.get('title'),best.get('uploader') or best.get('channel'),best.get('duration'),url)
subprocess.run([
  'yt-dlp','--no-playlist','--no-progress','--socket-timeout','30','--retries','4',
  '--js-runtimes','node','--remote-components','ejs:github',
  '--extractor-args','youtube:player_client=tv,web_safari',
  '--download-sections','*0-20','--force-keyframes-at-cuts',
  '-f','best[height<=720]/best','--merge-output-format','mp4',
  '-o','/tmp/next-story-probe.mp4',url
],check=True,timeout=600)
subprocess.run([
  'ffprobe','-v','error','-show_entries','format=duration,size',
  '-show_entries','stream=codec_type,codec_name,width,height',
  '-of','json','/tmp/next-story-probe.mp4'
],check=True)
print('NEXT_STORY_TRANSPORT_OK')
