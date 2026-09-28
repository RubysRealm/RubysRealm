#!/usr/bin/env python3
import json, subprocess, urllib.parse, urllib.request
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
proxy='https://rubys-realm.vercel.app/api/rubyclips-post?'+urllib.parse.urlencode({'pipedVideo':vid})
req=urllib.request.Request(proxy,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
with urllib.request.urlopen(req,timeout=60) as resp:
    data=json.loads(resp.read().decode())
print('PIPED',json.dumps(data)[:2000])
if not data.get('ok') or not str(data.get('hls') or '').startswith('http'):
    raise SystemExit('Piped proxy unavailable for next story')
hls=data['hls']
subprocess.run([
  'ffmpeg','-y','-hide_banner','-loglevel','error','-i',hls,'-t','20',
  '-map','0:v:0','-map','0:a:0?','-c:v','libx264','-preset','ultrafast','-crf','22',
  '-c:a','aac','-b:a','128k','/tmp/next-story-probe.mp4'
],check=True,timeout=600)
out=subprocess.check_output([
  'ffprobe','-v','error','-show_entries','format=duration,size',
  '-show_entries','stream=codec_type,codec_name,width,height','-of','json',
  '/tmp/next-story-probe.mp4'
],text=True)
print(out)
print('NEXT_STORY_TRANSPORT_OK')
