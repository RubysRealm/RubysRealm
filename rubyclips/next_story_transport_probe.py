#!/usr/bin/env python3
import json, subprocess, urllib.parse, urllib.request
vid='yGFMn5-D5nU'
proxy='https://rubys-realm.vercel.app/api/rubyclips-post?'+urllib.parse.urlencode({'pipedVideo':vid})
req=urllib.request.Request(proxy,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
try:
    with urllib.request.urlopen(req,timeout=60) as resp:
        data=json.loads(resp.read().decode())
except Exception as exc:
    raise SystemExit(f'PIPED_PROXY_ERROR {exc}')
print('PIPED',json.dumps(data)[:3000])
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
