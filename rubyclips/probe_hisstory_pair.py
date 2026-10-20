#!/usr/bin/env python3
import json, subprocess, urllib.request
from pathlib import Path

VIDEO_URL='https://www.facebook.com/HisYTStory/videos/his-mom-made-him-kneel-on-broken-glass-this-story-may-be-based-on-real-events-bu/1237986135113831/'
AUDIO_URL='https://anchor.fm/s/10ff75318/podcast/play/116612575/https%3A%2F%2Fd3ctxlq1ktw2nl.cloudfront.net%2Fstaging%2F2026-2-9%2F419591837-44100-2-b02f60a082077.mp3'
EXPECTED=168.0
OUT=Path('rubyclips/hisstory_pair_probe'); OUT.mkdir(parents=True,exist_ok=True)

def sh(cmd,timeout=900):
    print('+',' '.join(map(str,cmd)),flush=True)
    subprocess.run(cmd,check=True,timeout=timeout)

def probe(p):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)],text=True))

# Download full official visual. Its audio is deliberately ignored later.
visual=OUT/'visual.mp4'
sh(['yt-dlp','--no-playlist','--no-progress','--socket-timeout','30','--retries','5',
    '-f','bestvideo[height<=1080]/best[height<=1080]/best',
    '--merge-output-format','mp4','-o',str(visual),VIDEO_URL],timeout=900)

# Download only the official Spotify/Anchor RSS audio.
audio=OUT/'spotify-audio.mp3'
req=urllib.request.Request(AUDIO_URL,headers={'User-Agent':'Mozilla/5.0','Accept':'audio/mpeg,*/*'})
with urllib.request.urlopen(req,timeout=90) as r:
    audio.write_bytes(r.read())
if audio.stat().st_size<500000: raise RuntimeError('RSS audio too small')

vp=probe(visual); ap=probe(audio)
vd=float(vp['format']['duration']); ad=float(ap['format']['duration'])
if abs(vd-EXPECTED)>12: raise RuntimeError(f'Official visual duration mismatch {vd:.3f}')
if abs(ad-EXPECTED)>12: raise RuntimeError(f'Spotify audio duration mismatch {ad:.3f}')
if abs(vd-ad)>8: raise RuntimeError(f'Visual/audio length mismatch {vd:.3f} vs {ad:.3f}')
vs=[s for s in vp['streams'] if s.get('codec_type')=='video']
if not vs or int(vs[0].get('width') or 0)<300: raise RuntimeError('No real video stream')

# Create proof mux with Spotify audio replacing all source-platform sound.
mux=OUT/'paired.mp4'
dur=min(vd,ad)
sh(['ffmpeg','-y','-hide_banner','-loglevel','error',
    '-i',str(visual),'-i',str(audio),'-t',f'{dur:.3f}',
    '-map','0:v:0','-map','1:a:0',
    '-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(mux)],timeout=900)
mp=probe(mux)
ms=[s for s in mp['streams'] if s.get('codec_type')=='video']
ma=[s for s in mp['streams'] if s.get('codec_type')=='audio']
assert ms and ma
sh(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss','30','-i',str(mux),'-frames:v','1',str(OUT/'frame30.jpg')],timeout=90)

result={
 'ok':True,
 'visualUrl':VIDEO_URL,
 'audioUrl':AUDIO_URL,
 'visualDuration':vd,
 'spotifyAudioDuration':ad,
 'deltaSeconds':abs(vd-ad),
 'videoWidth':int(vs[0].get('width') or 0),
 'videoHeight':int(vs[0].get('height') or 0),
 'muxDuration':float(mp['format']['duration']),
 'muxBytes':mux.stat().st_size,
 'audioSource':'spotify-anchor-rss-only',
 'visualSourceAudioUsed':False
}
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
