#!/usr/bin/env python3
"""Rubaradaclips His Story pipeline.

Spotify/Anchor RSS is authoritative for episode order, title, duration and audio.
The matching official His Story Facebook video is used for visuals only.
No audio from Facebook/TikTok/YouTube is ever carried into the final MP4.
"""
import hashlib, html, json, math, os, re, shutil, subprocess, sys, textwrap
import urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
BASE=ROOT/'rubaradaclips_repurpose'
WORK=BASE/'work'; OUT=BASE/'output'; STATE_PATH=BASE/'state.json'
FEED='https://anchor.fm/s/10ff75318/podcast/rss'
SPOTIFY_SHOW_ID='6alyG1Jw4KH03mXZlYtPkf'
SPOTIFY_SHOW_URL=f'https://open.spotify.com/show/{SPOTIFY_SHOW_ID}'
SHOW_NAME='His Story: Animation Stories'
TARGET_CHANNEL='rubaradaclips'
TARGET_CHANNEL_ID='6a9f6ff1cd8b9c702c2897e1'
PART_TARGET=180
PART_MIN=105
PART_MAX=220
POST_HOURS=6
GENERATION=16
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
ITUNES='{http://www.itunes.com/dtds/podcast-1.0.dtd}'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'
PIPELINE_REVISION='avsync-v4-direct-builder'

# Proven exact official source; the resolver also discovers future entries automatically.
SOURCE_OVERRIDES={
    '8ffff3ff-ac10-4dee-8805-99b6979cdc63':
      'https://www.facebook.com/HisYTStory/videos/his-mom-made-him-kneel-on-broken-glass-this-story-may-be-based-on-real-events-bu/1237986135113831/',
}

def run(args,timeout=1200,capture=False):
    print('+',' '.join(map(str,args)),flush=True)
    p=subprocess.run(args,text=True,stdout=subprocess.PIPE if capture else None,
                     stderr=subprocess.STDOUT if capture else None,check=True,timeout=timeout)
    return p.stdout if capture else ''

def now(): return datetime.now(timezone.utc)
def iso(dt): return dt.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
def parse_time(v):
    if not v: return None
    try:return datetime.fromisoformat(str(v).replace('Z','+00:00'))
    except:return None
def safe(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def norm(s): return re.sub(r'[^a-z0-9]+',' ',safe(s).lower()).strip()
def compact(s): return re.sub(r'[^a-z0-9]+','',safe(s).lower())

def media_info(path):
    return json.loads(subprocess.check_output(
        ['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],
        text=True,timeout=90))

def duration_value(v):
    t=safe(v)
    if not t:return 0.0
    try:
        if ':' not in t:return float(t)
        n=0.0
        for p in t.split(':'): n=n*60+float(p)
        return n
    except:return 0.0

def series_id(guid):
    return 'hisstory-'+hashlib.sha256(guid.encode()).hexdigest()[:16]

def fetch_feed():
    req=urllib.request.Request(FEED,headers={'User-Agent':UA,'Accept':'application/rss+xml,application/xml,*/*'})
    xml=urllib.request.urlopen(req,timeout=90).read()
    root=ET.fromstring(xml)
    entries=[]
    for node in root.findall('./channel/item'):
        title=safe(node.findtext('title'))
        guid=safe(node.findtext('guid'))
        enc=node.find('enclosure')
        if not title or not guid or enc is None: continue
        audio=enc.attrib.get('url',''); mime=enc.attrib.get('type','')
        if not audio.startswith('https://') or mime not in ('audio/mpeg','audio/mp3'): continue
        try: date=parsedate_to_datetime(node.findtext('pubDate') or '').astimezone(timezone.utc)
        except: continue
        dur=duration_value(node.findtext(ITUNES+'duration'))
        if dur<20: continue
        cover_node=node.find(ITUNES+'image')
        cover=cover_node.attrib.get('href','') if cover_node is not None else ''
        entries.append({'guid':guid,'title':title,'date':iso(date),'audioUrl':audio,'mediaType':mime,
                        'duration':dur,'coverUrl':cover})
    entries.sort(key=lambda e:(e['date'],e['guid']))
    if len(entries)<200: raise RuntimeError(f'His Story RSS returned only {len(entries)} usable episodes')
    return entries

def load_state():
    if not STATE_PATH.exists(): raise RuntimeError('Missing Rubarataclips His Story state')
    s=json.loads(STATE_PATH.read_text())
    if s.get('feed')!=FEED or s.get('spotifyShowId')!=SPOTIFY_SHOW_ID:
        raise RuntimeError('State points to the wrong Spotify show')
    return s

def selected(state,entries):
    completed=set(state.get('completed') or [])
    cur=state.get('current') or {}
    if cur.get('guid'):
        ep=next((e for e in entries if e['guid']==cur['guid']),None)
        if ep is None: raise RuntimeError('Locked current episode disappeared from RSS')
        if ep['guid'] in completed: raise RuntimeError('Locked current episode is already completed')
        return ep,int(cur.get('next_part') or 1)
    ep=next((e for e in entries if e['guid'] not in completed),None)
    if ep is None:return None,1
    return ep,1

def segment_plan(duration):
    d=float(duration)
    if d<=PART_MAX:return [(0.0,d)]
    out=[]; start=0.0
    while d-start>PART_MAX:
        end=min(start+PART_TARGET,d)
        if 0<d-end<PART_MIN:end=d
        out.append((start,end)); start=end
    if d-start>1:out.append((start,d))
    if len(out)>=2 and out[-1][1]-out[-1][0]<70:
        out[-2]=(out[-2][0],out[-1][1]);out.pop()
    return out

class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.href=None;self.txt=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()=='a':self.href=dict(attrs).get('href');self.txt=[]
    def handle_data(self,data):
        if self.href is not None:self.txt.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=='a' and self.href is not None:
            self.rows.append((self.href,' '.join(self.txt)));self.href=None;self.txt=[]

def http_text(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    return urllib.request.urlopen(req,timeout=35).read().decode('utf-8','replace')

def ddg_candidates(title):
    queries=[f'"{title}" "His Story"',f'"{title}" HisYTStory']
    found=[]
    for query in queries:
        try:
            url='https://html.duckduckgo.com/html/?q='+urllib.parse.quote_plus(query)
            page=http_text(url);p=Links();p.feed(page)
            for href,text in p.rows:
                href=html.unescape(href or '')
                if href.startswith('//'):href='https:'+href
                elif href.startswith('/'):href=urllib.parse.urljoin(url,href)
                if 'duckduckgo.com/l/' in href:
                    q=urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if q.get('uddg'):href=q['uddg'][0]
                href=href.split('&rut=')[0]
                if 'facebook.com/HisYTStory/videos/' in href and href not in [x['url'] for x in found]:
                    found.append({'url':href,'anchor':safe(text)})
        except Exception as exc:
            print('Search query failed:',query,exc,flush=True)
    return found

def meta(url):
    raw=run(['yt-dlp','--no-playlist','--skip-download','--dump-single-json','--no-warnings',
             '--socket-timeout','30','--retries','4',url],timeout=240,capture=True)
    lines=[x for x in raw.splitlines() if x.strip().startswith('{')]
    if not lines:raise RuntimeError('No metadata JSON')
    return json.loads(lines[-1])

def title_score(a,b):
    aa=set(norm(a).split());bb=set(norm(b).split())
    return len(aa&bb)/max(1,len(aa))

def resolve_visual(ep):
    override=SOURCE_OVERRIDES.get(ep['guid'])
    candidates=[{'url':override,'anchor':ep['title']}] if override else []
    candidates+=ddg_candidates(ep['title'])
    errors=[]
    for row in candidates:
        try:
            m=meta(row['url']); title=safe(m.get('title') or row['anchor'])
            dur=float(m.get('duration') or 0)
            score=title_score(ep['title'],title)
            delta=abs(dur-ep['duration'])
            tolerance=max(12.0,ep['duration']*0.10)
            if score<0.60:raise RuntimeError(f'title score {score:.2f}')
            if dur<=0 or delta>tolerance:raise RuntimeError(f'duration mismatch {dur:.2f} vs {ep["duration"]:.2f}')
            return {'url':row['url'],'id':str(m.get('id') or ''),'title':title,'duration':dur,
                    'score':score,'delta':delta}
        except Exception as exc:errors.append(f'{row.get("url")}: {exc}')
    raise RuntimeError('No verified official His Story visual found. '+'; '.join(errors[:8]))

def download_visual_segment(url,start,end,dest):
    dest.unlink(missing_ok=True)
    section=f'*{start:.3f}-{end:.3f}'
    run(['yt-dlp','--no-playlist','--no-progress','--socket-timeout','30','--retries','5',
         '--download-sections',section,
         '-f','bestvideo[height<=1080]/best[height<=1080]/best',
         '--merge-output-format','mp4','-o',str(dest),url],timeout=900)
    if not dest.exists() or dest.stat().st_size<200000:raise RuntimeError('Visual segment missing/too small')

def build_audio_segment(url,start,seconds,dest):
    dest.unlink(missing_ok=True)
    run(['ffmpeg','-y','-hide_banner','-loglevel','error','-rw_timeout','60000000',
         '-ss',f'{start:.3f}','-i',url,'-t',f'{seconds:.3f}',
         '-vn','-ac','2','-ar','48000','-c:a','aac','-b:a','192k',str(dest)],timeout=480)
    if not dest.exists() or dest.stat().st_size<100000:raise RuntimeError('Spotify audio segment missing')

def safe_title(title):
    lines=textwrap.wrap(safe(title),width=34,break_long_words=False,break_on_hyphens=False)
    if len(lines)>2:
        lines=lines[:2]
        if len(lines[-1])>3:lines[-1]=lines[-1][:-3].rstrip()+'...'
    return '\n'.join(lines) or 'His Story'

def render(visual,audio,title,index,total,dest):
    vinfo=media_info(visual)
    vs=[s for s in vinfo['streams'] if s.get('codec_type')=='video']
    if not vs:raise RuntimeError('Resolved visual has no video stream')
    sw=max(1,int(vs[0].get('width') or 1));sh=max(1,int(vs[0].get('height') or 1))
    scale=min(1000.0/sw,1000.0/sh);fg_h=sh*scale
    picture_top=(1920.0-fg_h)/2.0+160.0;gap_mid=picture_top/2.0
    box_h=260;box_y=max(35,int(round(gap_mid-box_h/2.0)));title_y=box_y+34;part_y=box_y+180
    title_file=WORK/'title.txt';part_file=WORK/'part.txt'
    title_file.write_text(safe_title(title));part_file.write_text(f'PART {index} OF {total}')
    vf=(
      '[0:v]split=2[bg0][fg0];'
      '[bg0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=32[bg];'
      '[fg0]scale=1000:1000:force_original_aspect_ratio=decrease[fg];'
      '[bg][fg]overlay=(W-w)/2:(H-h)/2+160[base];'
      f'[base]drawbox=x=45:y={box_y}:w=990:h={box_h}:color=black@0.60:t=fill,'
      f'drawtext=fontfile={FONT}:textfile={title_file.as_posix()}:fontcolor=white:fontsize=44:'
      f'line_spacing=12:x=(w-text_w)/2:y={title_y},'
      f'drawtext=fontfile={FONT}:textfile={part_file.as_posix()}:fontcolor=white:fontsize=50:'
      f'x=(w-text_w)/2:y={part_y}[v]'
    )
    run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(visual),'-i',str(audio),
         '-filter_complex',vf,'-map','[v]','-map','1:a:0','-r','30',
         '-c:v','libx264','-preset','medium','-crf','20','-pix_fmt','yuv420p',
         '-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart','-shortest',str(dest)],timeout=1500)

def verify_final(path,expected):
    info=media_info(path);vs=[s for s in info['streams'] if s.get('codec_type')=='video'];aa=[s for s in info['streams'] if s.get('codec_type')=='audio']
    if len(vs)!=1 or len(aa)!=1:raise RuntimeError('Final output missing one audio/video stream')
    if vs[0].get('codec_name')!='h264' or aa[0].get('codec_name')!='aac':raise RuntimeError('Wrong final codecs')
    if (int(vs[0].get('width') or 0),int(vs[0].get('height') or 0))!=(1080,1920):raise RuntimeError('Final output is not 1080x1920')
    dur=float(info['format']['duration'])
    if not expected-5<=dur<=expected+3:raise RuntimeError(f'Final duration mismatch {dur:.2f} expected {expected:.2f}')
    if path.stat().st_size<500000:raise RuntimeError('Final output too small')
    # Motion check: two distant frames must not be identical.
    f1=WORK/'motion1.jpg';f2=WORK/'motion2.jpg'
    t1=min(8,max(1,dur*.15));t2=min(max(t1+8,dur*.65),max(t1+1,dur-2))
    for t,p in ((t1,f1),(t2,f2)):
        run(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss',f'{t:.2f}','-i',str(path),'-frames:v','1',str(p)],timeout=90)
    if hashlib.sha256(f1.read_bytes()).digest()==hashlib.sha256(f2.read_bytes()).digest():
        raise RuntimeError('Motion check failed: output appears static')
    return dur

def check():
    state=load_state();entries=fetch_feed();ep,part=selected(state,entries)
    allowed=ep is not None;reason='ready'
    last=parse_time(state.get('last_post_at'))
    if last and now()-last<timedelta(hours=POST_HOURS):allowed=False;reason='6-hour cadence'
    if state.get('hold'):allowed=False;reason='manual hold'
    data={'allowed':allowed,'reason':reason,'current':ep['title'] if ep else None,'part':part,
          'lastPostAt':state.get('last_post_at'),'episodes':len(entries)}
    print(json.dumps(data,indent=2))
    gp=os.environ.get('GITHUB_OUTPUT')
    if gp:
        with open(gp,'a') as f:f.write('allowed='+('true' if allowed else 'false')+'\n')
    return allowed

def build():
    shutil.rmtree(WORK,ignore_errors=True);shutil.rmtree(OUT,ignore_errors=True);WORK.mkdir(parents=True);OUT.mkdir(parents=True)
    state=load_state();entries=fetch_feed();ep,part=selected(state,entries)
    if ep is None:raise RuntimeError('His Story queue is complete')
    segments=segment_plan(ep['duration'])
    if part<1 or part>len(segments):raise RuntimeError(f'Invalid locked part {part} of {len(segments)}')
    start,end=segments[part-1];seconds=end-start
    resolved=resolve_visual(ep)
    visual=WORK/'visual.mp4';audio=WORK/'spotify-audio.m4a'
    download_visual_segment(resolved['url'],start,end,visual)
    build_audio_segment(ep['audioUrl'],start,seconds,audio)
    # Segment lengths must still align before rendering.
    vd=float(media_info(visual)['format']['duration']);ad=float(media_info(audio)['format']['duration'])
    if abs(vd-ad)>5:raise RuntimeError(f'Part visual/audio mismatch {vd:.2f}s vs {ad:.2f}s')
    sid=series_id(ep['guid']);filename=f'hisstory-{sid}-r{GENERATION}-part-{part:02d}.mp4';dest=OUT/filename
    render(visual,audio,ep['title'],part,len(segments),dest)
    dur=verify_final(dest,seconds)
    story_tag='#'+re.sub(r'[^A-Za-z0-9]','',ep['title'])[:38]
    if story_tag=='#':story_tag='#HisStory'
    caption=f'{ep["title"]} — Part {part} of {len(segments)} {story_tag} #rubaradaclips #storytime'
    logical=f'rubyclips:{sid}:r{GENERATION}:p{part}';tag=f'rubyclips-tt-{sid}-r{GENERATION}-p{part}'
    manifest={
      'platform':'rubyclips-tiktok-story-v1','pipelineRevision':PIPELINE_REVISION,
      'sourceProvider':'hisstory-spotify-rss','sourceChannel':'his story: animation stories',
      'sourceSeriesId':sid,'sourceSeriesTitle':ep['title'],'sourceVideoIds':[ep['guid']],'sourceUrls':[FEED],
      'sourceEpisodeGuid':ep['guid'],'sourceMediaType':ep['mediaType'],'spotifyShowId':SPOTIFY_SHOW_ID,
      'spotifyShowUrl':SPOTIFY_SHOW_URL,'transportProvider':'facebook-official-hisstory-video-only',
      'transportUrl':resolved['url'],'transportVideoId':resolved['id'],'transportAudioUsed':False,
      'restartGeneration':GENERATION,'logicalPostKey':logical,'segmentIndex':part,'segmentTotal':len(segments),
      'segmentDurationSeconds':round(dur,3),'file':filename,'targetChannel':TARGET_CHANNEL,'caption':caption,
      'storyHashtag':story_tag,'titleBurnedIn':True,'partLabelBurnedIn':True,'thumbnailOffsetMs':1000
    }
    info={'guid':ep['guid'],'title':ep['title'],'date':ep['date'],'part':part,'totalParts':len(segments),
          'startSeconds':start,'endSeconds':end,'duration':round(dur,3),'logicalPostKey':logical,
          'releaseTag':tag,'visualUrl':resolved['url'],'spotifyAudioUrl':ep['audioUrl']}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (OUT/'part-info.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps({'ok':True,'manifest':manifest,'partInfo':info,'bytes':dest.stat().st_size},indent=2))

def advance(sent_file):
    state=load_state();info=json.loads((OUT/'part-info.json').read_text());sent=json.loads(Path(sent_file).read_text());post=sent.get('post') or {}
    if sent.get('ok') is not True or str(post.get('status') or '').lower()!='sent':raise RuntimeError('Cannot advance without confirmed TikTok send')
    if str((post.get('channel') or {}).get('id'))!=TARGET_CHANNEL_ID:raise RuntimeError('Wrong TikTok channel')
    link=str(post.get('externalLink') or '')
    if 'tiktok.com/@rubaradaclips/video/' not in link or not parse_time(post.get('sentAt')):raise RuntimeError('TikTok link/sentAt not confirmed')
    cur=state.get('current') or {}
    if cur.get('guid')!=info['guid'] or int(cur.get('next_part') or 0)!=int(info['part']):
        if state.get('last_logical_post_key')==info['logicalPostKey']:
            print('Already advanced',info['logicalPostKey']);return
        raise RuntimeError('Refusing stale/out-of-order queue advance')
    state['last_post_at']=post['sentAt'];state['last_tiktok_link']=link;state['last_buffer_post_id']=post.get('id');state['last_logical_post_key']=info['logicalPostKey']
    if int(info['part'])>=int(info['totalParts']):
        done=list(state.get('completed') or [])
        if info['guid'] not in done:done.append(info['guid'])
        state['completed']=done
        entries=fetch_feed();nxt=next((e for e in entries if e['guid'] not in set(done)),None)
        state['current']={'guid':nxt['guid'],'title':nxt['title'],'next_part':1} if nxt else None
    else:
        state['current']={'guid':info['guid'],'title':info['title'],'next_part':int(info['part'])+1}
    STATE_PATH.write_text(json.dumps(state,indent=2)+'\n')
    print(json.dumps({'advanced':True,'lastPostAt':state['last_post_at'],'tiktok':link,'next':state.get('current')},indent=2))

if __name__=='__main__':
    if len(sys.argv)<2:raise SystemExit('Usage: pipeline.py check|build|advance status.json')
    if sys.argv[1]=='check':check()
    elif sys.argv[1]=='build':build()
    elif sys.argv[1]=='advance':advance(sys.argv[2])
    else:raise SystemExit('Invalid command')
