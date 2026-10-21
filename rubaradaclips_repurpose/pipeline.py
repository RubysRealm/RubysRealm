#!/usr/bin/env python3
"""Rubaradaclips His Story pipeline.

Spotify/Anchor identifies the chronological queue and supplies episode sound.
The source adapter verifies the full original video before the existing renderer
cuts contiguous parts from the precise Spotify duration, including the ending.
Pending releases are reconciled before any source request or media rebuild.
"""
import argparse, hashlib, json, math, os, re, subprocess, sys, tempfile
import urllib.error, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
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
POST_HOURS=6
GENERATION=16
ITUNES='{http://www.itunes.com/dtds/podcast-1.0.dtd}'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'
PIPELINE_REVISION='avsync-v6-centered-inter-title'
CATALOG_PATH=ROOT/'rubyclips'/'spotify_video_catalog.json'
PUBLISHER='https://rubys-realm.vercel.app/api/rubyclips-post'
PUBLISHER_VERSION='hisstory-v17-durable-video'
BUFFER_ORG_ID='6a909de43dfa01f80e2d23c6'
REPO='RubysRealm/RubysRealm'
UNKNOWN_GRACE=timedelta(minutes=15)
ABSENT_INTERVAL=timedelta(minutes=5)

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
    """Freeze contiguous 180-second parts from the precise full source duration."""
    duration=float(duration)
    if not math.isfinite(duration) or duration<=0:
        raise RuntimeError('Invalid full original episode duration')
    count=max(1,math.ceil(duration/PART_TARGET))
    if count>1 and duration-(count-1)*PART_TARGET<=0.15:
        count-=1
    return [(float(i*PART_TARGET), min(float((i+1)*PART_TARGET),duration)
             if i<count-1 else duration) for i in range(count)]

def render(visual,audio,title,index,total,dest,start=0.0,seconds=None):
    # Keep typography dependencies out of the pre-install queue/recovery checks.
    if __package__:
        from .title_card import create_title_card
    else:
        from title_card import create_title_card
    vinfo=media_info(visual)
    vs=[s for s in vinfo['streams'] if s.get('codec_type')=='video']
    if not vs:raise RuntimeError('Resolved visual has no video stream')
    sw=max(1,int(vs[0].get('width') or 1));sh=max(1,int(vs[0].get('height') or 1))
    scale=min(1000.0/sw,1000.0/sh);fg_h=sh*scale
    picture_top=(1920.0-fg_h)/2.0+160.0
    title_card=WORK/'title-card.png'
    layout=create_title_card(title,index,total,picture_top,title_card)
    (WORK/'title-layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    vf=(
      '[0:v]split=2[bg0][fg0];'
      '[bg0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=32[bg];'
      '[fg0]scale=1000:1000:force_original_aspect_ratio=decrease[fg];'
      '[bg][fg]overlay=(W-w)/2:(H-h)/2+160[base];'
      '[base][2:v]overlay=0:0:eof_action=repeat:repeatlast=1:format=auto,format=yuv420p[v]'
    )
    run(['ffmpeg','-y','-hide_banner','-loglevel','error',
         '-ss',f'{start:.6f}','-i',str(visual),'-ss',f'{start:.6f}','-i',str(audio),
         '-i',str(title_card),
         *(['-t',f'{seconds:.6f}'] if seconds is not None else []),
         '-filter_complex_threads','2','-filter_complex',vf,'-map','[v]','-map','1:a:0','-r','30',
         '-c:v','libx264','-preset','medium','-crf','20','-pix_fmt','yuv420p',
         '-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(dest)],timeout=1500)
    return layout

def verify_final(path,expected):
    info=media_info(path);vs=[s for s in info['streams'] if s.get('codec_type')=='video'];aa=[s for s in info['streams'] if s.get('codec_type')=='audio']
    if len(vs)!=1 or len(aa)!=1:raise RuntimeError('Final output missing one audio/video stream')
    if vs[0].get('codec_name')!='h264' or aa[0].get('codec_name')!='aac':raise RuntimeError('Wrong final codecs')
    if (int(vs[0].get('width') or 0),int(vs[0].get('height') or 0))!=(1080,1920):raise RuntimeError('Final output is not 1080x1920')
    dur=float(info['format']['duration'])
    if not expected-0.2<=dur<=expected+0.2:raise RuntimeError(f'Final duration mismatch {dur:.6f} expected {expected:.6f}')
    for stream in (vs[0],aa[0]):
        stream_duration=float(stream.get('duration') or 0)
        if not expected-0.2<=stream_duration<=expected+0.2:
            raise RuntimeError(f'Final {stream["codec_type"]} does not cover the complete planned segment')
    if path.stat().st_size<500000:raise RuntimeError('Final output too small')
    # Motion check: two distant frames must not be identical.
    f1=WORK/'motion1.jpg';f2=WORK/'motion2.jpg'
    t1=min(8,max(1,dur*.15));t2=min(max(t1+8,dur*.65),max(t1+1,dur-2))
    for t,p in ((t1,f1),(t2,f2)):
        run(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss',f'{t:.2f}','-i',str(path),'-frames:v','1',str(p)],timeout=90)
    if hashlib.sha256(f1.read_bytes()).digest()==hashlib.sha256(f2.read_bytes()).digest():
        raise RuntimeError('Motion check failed: output appears static')
    return dur


class QueueError(RuntimeError):
    pass


class APIError(QueueError):
    def __init__(self,message,status=None):
        super().__init__(message)
        self.status=status


def require(condition,message):
    if not condition:
        raise QueueError(message)


def release_identity(guid,part):
    sid=series_id(guid)
    return f'rubyclips-tt-{sid}-r{GENERATION}-p{part}',f'rubyclips:{sid}:r{GENERATION}:p{part}'


def release_video_url(tag,filename):
    require(re.fullmatch(r'[A-Za-z0-9_.-]+\.mp4',filename),'Invalid immutable video filename')
    return f'https://github.com/{REPO}/releases/download/{tag}/{filename}'


def ensure_catalog_guid(guid):
    """Refresh once when the live feed reaches an episode newer than the cache."""
    cached=json.loads(CATALOG_PATH.read_text()) if CATALOG_PATH.exists() else {}
    if any(row.get('rssGuid')==guid for row in cached.get('episodes',[])):
        return
    command=[sys.executable,str(ROOT/'rubyclips'/'spotify_video_source.py'),
             'refresh-catalog','--catalog',str(CATALOG_PATH)]
    result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=600)
    require(result.returncode==0,'The new Spotify episode catalog could not be refreshed; keep this episode queued')
    refreshed=json.loads(CATALOG_PATH.read_text())
    require(any(row.get('rssGuid')==guid for row in refreshed.get('episodes',[])),
            'The current RSS episode has no exact Spotify mapping after refresh; keep it queued')


def build_verified(state):
    """Use the existing presentation with a verified full source and precise cuts."""
    entries=fetch_feed()
    ep,part=selected(state,entries)
    if ep is None:
        return None
    ensure_catalog_guid(ep['guid'])
    WORK.mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
    # acquire writes source-info only after full audio/video identity and coverage
    # checks pass. No unverified fallback media is usable by this renderer.
    source_dir=WORK/'verified-source'
    command=[sys.executable,str(ROOT/'rubyclips'/'spotify_video_source.py'),'acquire',
             '--rss-guid',ep['guid'],'--output-dir',str(source_dir),'--catalog',str(CATALOG_PATH)]
    result=subprocess.run(command,cwd=ROOT,text=True,capture_output=True,timeout=2400)
    if result.returncode:
        message=result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'Original episode video is unavailable'
        try:
            message=json.loads(message).get('error',message)
        except (ValueError,AttributeError):
            pass
        raise QueueError(str(message)[:700])
    evidence=json.loads((source_dir/'source-info.json').read_text())
    require(evidence.get('ok') is True and evidence.get('spotifyShowId')==SPOTIFY_SHOW_ID,
            'Source adapter returned a different show')
    require(evidence.get('rssGuid')==ep['guid'],'Source adapter returned a different RSS episode')
    for key in ('sourceVideoVerified','sourceAudioVerified','fullEpisodeVerified'):
        require(evidence.get(key) is True,'Source adapter has not verified '+key)
    media=evidence.get('sourceMedia') or {}
    require(media.get('fullEpisode') is True and media.get('videoCodec') and media.get('audioCodec'),
            'Full original source must contain both video and audio')
    source_duration=float(evidence['sourceDurationSeconds'])
    require(source_duration>0 and math.isfinite(source_duration),'Invalid precise source duration')
    for key in ('videoDurationSeconds','audioDurationSeconds'):
        require(float(media.get(key) or 0)>=source_duration-0.2,
                'Full original source does not cover the episode ending')
    source=Path(evidence['file']).resolve()
    require(source== (source_dir/'full-source.mp4').resolve() and source.is_file(),
            'Source adapter returned an unexpected media path')
    current=state.get('current') or {'guid':ep['guid'],'title':ep['title'],'next_part':part}
    if current.get('segments'):
        require(abs(float(current['sourceDurationSeconds'])-source_duration)<=0.2,
                'The full source duration changed after this episode started')
        segments=[(float(a),float(b)) for a,b in current['segments']]
        require(segments[0][0]==0 and abs(segments[-1][1]-source_duration)<=0.2 and
                all(a<b and (i==0 or abs(a-segments[i-1][1])<0.000001)
                    for i,(a,b) in enumerate(segments)),'Saved part plan is not contiguous')
    else:
        segments=segment_plan(source_duration)
        current.update({'spotifyEpisodeId':evidence['episodeId'],
                        'sourceDurationSeconds':source_duration,'segments':segments})
    require(1<=part<=len(segments),'The locked part is outside the complete source')
    state['current']=current
    start,end=segments[part-1]
    seconds=end-start
    sid=series_id(ep['guid'])
    filename=f'hisstory-{sid}-r{GENERATION}-part-{part:02d}.mp4'
    dest=OUT/filename
    title_layout=render(source,source,ep['title'],part,len(segments),dest,start=start,seconds=seconds)
    duration=verify_final(dest,seconds)
    final=media_info(dest)
    video=next(s for s in final['streams'] if s.get('codec_type')=='video')
    audio=next(s for s in final['streams'] if s.get('codec_type')=='audio')
    story_tag='#'+re.sub(r'[^A-Za-z0-9]','',ep['title'])[:38]
    if story_tag=='#':
        story_tag='#HisStory'
    caption=f'{ep["title"]} — Part {part} of {len(segments)} {story_tag} #rubaradaclips #storytime'
    tag,logical=release_identity(ep['guid'],part)
    verification=evidence.get('sourceVerification') or {}
    manifest={
        'platform':'rubyclips-tiktok-story-v1','pipelineRevision':PIPELINE_REVISION,
        'sourceProvider':'hisstory-spotify-rss','sourceChannel':'his story: animation stories',
        'sourceSeriesId':sid,'sourceSeriesTitle':ep['title'],'sourceVideoIds':[ep['guid']],
        'sourceUrls':[FEED],'sourceEpisodeGuid':ep['guid'],'sourceMediaType':ep['mediaType'],
        'spotifyShowId':SPOTIFY_SHOW_ID,'spotifyShowUrl':SPOTIFY_SHOW_URL,
        'spotifyEpisodeId':evidence['episodeId'],'sourceSpotifyEpisodeId':evidence['episodeId'],
        'transportProvider':evidence['sourceAccessMethod'],
        'transportUrl':verification.get('visualUrl') or f'https://open.spotify.com/episode/{evidence["episodeId"]}',
        'transportVideoId':verification.get('visualId'),'transportAudioUsed':False,
        'restartGeneration':GENERATION,'logicalPostKey':logical,
        'segmentIndex':part,'segmentTotal':len(segments),
        'segmentStartSeconds':start,'segmentEndSeconds':end,
        'segmentDurationSeconds':round(duration,6),'plannedDurationSeconds':seconds,
        'sourceDurationSeconds':source_duration,'sourceMedia':media,
        'sourceVideoVerified':True,'sourceAudioVerified':True,'fullEpisodeVerified':True,
        'sourceAccessMethod':evidence['sourceAccessMethod'],'sourceSha256':evidence['sourceSha256'],
        'mediaVideo':{'codec':'h264','width':1080,'height':1920,'durationSeconds':float(video['duration'])},
        'mediaAudio':{'codec':'aac','durationSeconds':float(audio['duration'])},
        'visualMode':'original-source-video','outputVideoCodec':'h264','outputAudioCodec':'aac',
        'mediaSha256':hashlib.sha256(dest.read_bytes()).hexdigest(),
        'file':filename,'targetChannel':TARGET_CHANNEL,'caption':caption,
        'storyHashtag':story_tag,'titleBurnedIn':True,'partLabelBurnedIn':True,'thumbnailOffsetMs':1000,
        'titleLayout':title_layout,
    }
    if verification:
        manifest['sourceVerification']=verification
    done=set(state.get('completed') or [])|{ep['guid']}
    next_episode=next((row for row in entries if row['guid'] not in done),None)
    info={'guid':ep['guid'],'spotifyEpisodeId':evidence['episodeId'],'title':ep['title'],
          'date':ep['date'],'part':part,'totalParts':len(segments),'startSeconds':start,'endSeconds':end,
          'sourceDurationSeconds':source_duration,'duration':round(duration,6),
          'logicalPostKey':logical,'releaseTag':tag,'file':filename,'caption':caption,
          'nextEpisode':({'guid':next_episode['guid'],'title':next_episode['title'],'next_part':1}
                         if next_episode else None)}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (OUT/'part-info.json').write_text(json.dumps(info,indent=2)+'\n')
    return manifest,info


class RepositoryIO:
    def __init__(self,persist=False):
        self.persist=persist

    @staticmethod
    def command(args,timeout=120,check=True):
        result=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=timeout)
        if check and result.returncode:
            raise QueueError(f'{args[0]} failed: {result.stderr.strip()[-600:]}')
        return result

    def save_state(self,state,reason):
        temporary=STATE_PATH.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(state,indent=2)+'\n')
        os.replace(temporary,STATE_PATH)
        if not self.persist:
            return
        paths=[str(STATE_PATH.relative_to(ROOT))]
        if CATALOG_PATH.exists():
            paths.append(str(CATALOG_PATH.relative_to(ROOT)))
        self.command(['git','config','user.name','rubaradaclips-publisher-bot'])
        self.command(['git','config','user.email','actions@users.noreply.github.com'])
        self.command(['git','add','--',*paths])
        if self.command(['git','diff','--cached','--quiet','--',*paths],check=False).returncode==0:
            return
        self.command(['git','commit','-m',reason+' [skip ci]','--',*paths])
        for _ in range(3):
            self.command(['git','pull','--rebase','origin','main'])
            if self.command(['git','push','origin','HEAD:main'],check=False).returncode==0:
                return
        raise QueueError('State could not be saved remotely; refusing further posting')

    @staticmethod
    def request(parameters):
        request=urllib.request.Request(PUBLISHER+'?'+urllib.parse.urlencode(parameters),
                    headers={'Accept':'application/json','Cache-Control':'no-cache'})
        try:
            with urllib.request.urlopen(request,timeout=150) as response:
                data=json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                body=json.loads(exc.read().decode())
            except (ValueError,UnicodeError):
                body={}
            raise APIError(body.get('error') or body.get('message') or f'HTTP {exc.code}',exc.code) from exc
        except (urllib.error.URLError,TimeoutError,ValueError) as exc:
            raise APIError('Publisher response could not be verified: '+type(exc).__name__) from exc
        if data.get('ok') is not True:
            raise APIError(str(data.get('error') or 'Publisher returned no verified result'))
        return data

    def lookup(self,pending):
        return self.request({'lookupTag':pending['releaseTag']})

    def publish(self,pending):
        return self.request({'tag':pending['releaseTag']})

    def health(self):
        data=self.request({'health':'1'})
        require(data.get('channelName')==TARGET_CHANNEL and data.get('version')==PUBLISHER_VERSION,
                'The durable His Story publisher deployment is not ready')

    def find_release(self,tag):
        result=self.command(['gh','release','view',tag,'--repo',REPO,'--json','tagName,createdAt,assets'],check=False)
        if result.returncode:
            if re.search(r'not found|404',result.stderr,re.I):
                return None
            raise QueueError('Could not verify whether the current immutable release exists')
        release=json.loads(result.stdout)
        names={asset['name'] for asset in release.get('assets',[])}
        require('manifest.json' in names,'Current release has no immutable manifest')
        with tempfile.TemporaryDirectory(prefix='hisstory-recovery-') as directory:
            args=['gh','release','download',tag,'--repo',REPO,'--dir',directory,'--pattern','manifest.json']
            for optional in ('part-info.json','publish.json'):
                if optional in names:
                    args+=['--pattern',optional]
            self.command(args)
            path=Path(directory)
            manifest=json.loads((path/'manifest.json').read_text())
            require(manifest.get('file') in names,'The immutable release video asset is missing')
            info=json.loads((path/'part-info.json').read_text()) if 'part-info.json' in names else None
            receipt=json.loads((path/'publish.json').read_text()) if 'publish.json' in names else None
        return {'manifest':manifest,'info':info,'receipt':receipt,'createdAt':release.get('createdAt')}

    def build(self,state):
        return build_verified(state)

    def ensure_release(self,manifest,info):
        existing=self.find_release(info['releaseTag'])
        if existing:
            # Published media and manifest are never overwritten by a rerun.
            return existing,False
        self.command(['gh','release','create',info['releaseTag'],'--repo',REPO,
                      str(OUT/manifest['file']),str(OUT/'manifest.json'),str(OUT/'part-info.json'),
                      '--title','Rubarataclips His Story part',
                      '--notes','Verified original source video and Spotify audio. Durable queue advances only after confirmed TikTok send.'],
                     timeout=900)
        return {'manifest':manifest,'info':info,'receipt':None},True

    def write_receipt(self,pending):
        receipt={'ok':True,'postId':pending['postId'],'channelName':TARGET_CHANNEL,
                 'channelId':TARGET_CHANNEL_ID,'releaseTag':pending['releaseTag'],
                 'logicalPostKey':pending['logicalPostKey'],'videoUrl':pending['videoUrl'],
                 'caption':pending['caption'],'submittedAt':pending.get('submittedAt')}
        with tempfile.TemporaryDirectory(prefix='hisstory-receipt-') as directory:
            path=Path(directory)/'publish.json'
            result=self.command(['gh','release','download',pending['releaseTag'],'--repo',REPO,
                                 '--pattern','publish.json','--dir',directory],check=False)
            if result.returncode==0:
                previous=json.loads(path.read_text())
                require(previous.get('postId')==pending['postId'],'Release receipt points to a different Buffer attempt')
                return
            if not re.search(r'no assets|not found|404|no matching',result.stderr,re.I):
                raise QueueError('Could not check existing immutable publish receipt')
            path.write_text(json.dumps(receipt,indent=2)+'\n')
            self.command(['gh','release','upload',pending['releaseTag'],'--repo',REPO,str(path)])


class DurableQueue:
    def __init__(self,state,io,clock=now):
        self.state=state
        self.io=io
        self.clock=clock
        require(state.get('feed')==FEED and state.get('spotifyShowId')==SPOTIFY_SHOW_ID,
                'Queue is pinned to a different Spotify source')
        require(state.get('targetChannel')==TARGET_CHANNEL,'Queue is pinned to a different TikTok account')

    def save(self,reason):
        self.io.save_state(self.state,reason)

    def result(self,status,**extra):
        result={'status':status,'allowed':status=='needs_prepare',
                'pending':bool(self.state.get('pending')),
                'current':self.state.get('current'),'lastPostAt':self.state.get('last_post_at'),**extra}
        return result

    def due(self):
        if self.state.get('hold'):
            return False
        last=parse_time(self.state.get('last_post_at'))
        require(last is None or last.tzinfo is not None,'Last confirmed post timestamp has no time zone')
        return last is None or self.clock()-last>=timedelta(hours=POST_HOURS)

    def adopt(self,release,tag,known_new=False):
        manifest=release['manifest']
        info=release.get('info') or {}
        guid=manifest.get('sourceEpisodeGuid')
        part=int(manifest.get('segmentIndex') or 0)
        total=int(manifest.get('segmentTotal') or 0)
        expected_tag,logical=release_identity(guid or '',part)
        current=self.state.get('current') or {}
        require(guid and current.get('guid')==guid and int(current.get('next_part') or 0)==part,
                'Immutable release is not the current queue part')
        require(expected_tag==tag and manifest.get('logicalPostKey')==logical and
                manifest.get('spotifyShowId')==SPOTIFY_SHOW_ID and manifest.get('targetChannel')==TARGET_CHANNEL,
                'Immutable release identity does not match this account and source')
        require(1<=part<=total and manifest.get('caption'),'Invalid immutable episode part')
        if info:
            require(info.get('guid')==guid and info.get('part')==part and info.get('totalParts')==total
                    and info.get('logicalPostKey')==logical and info.get('releaseTag')==tag,
                    'Release part-info does not match the immutable manifest')
        pending={'releaseTag':tag,'logicalPostKey':logical,'guid':guid,
                 'spotifyEpisodeId':manifest.get('spotifyEpisodeId'),'part':part,'totalParts':total,
                 'title':manifest.get('sourceSeriesTitle'),'file':manifest['file'],'caption':manifest['caption'],
                 'videoUrl':release_video_url(tag,manifest['file']),
                 'startSeconds':info.get('startSeconds',manifest.get('segmentStartSeconds')),
                 'endSeconds':info.get('endSeconds',manifest.get('segmentEndSeconds')),
                 'sourceDurationSeconds':manifest.get('sourceDurationSeconds'),
                 'nextEpisode':info.get('nextEpisode'),'preparedAt':iso(self.clock()),
                 'phase':'prepared' if known_new else 'submission_unknown',
                 'verifiedSource':manifest.get('fullEpisodeVerified') is True}
        receipt=release.get('receipt')
        if receipt:
            require(receipt.get('ok') is True and receipt.get('postId') and
                    receipt.get('channelName')==TARGET_CHANNEL,'Invalid existing Buffer receipt')
            require(not receipt.get('channelId') or receipt['channelId']==TARGET_CHANNEL_ID,
                    'Buffer receipt belongs to a different account')
            require(not receipt.get('videoUrl') or receipt['videoUrl']==pending['videoUrl'],
                    'Buffer receipt belongs to a different video')
            pending.update({'postId':receipt['postId'],'phase':'accepted'})
        if not known_new:
            pending['submittedAt']=iso(self.clock())
        self.state['pending']=pending
        self.state.pop('source_blocked',None)
        self.save('Persist current His Story release before any publish request')

    def tick(self,prepare=False):
        if self.state.get('pending'):
            return self.reconcile()
        current=self.state.get('current') or {}
        if current.get('guid'):
            tag,_=release_identity(current['guid'],int(current.get('next_part') or 1))
            try:
                release=self.io.find_release(tag)
            except QueueError as exc:
                return self.result('waiting',reason=str(exc))
            if release:
                self.adopt(release,tag)
                return self.reconcile()
        if not self.due():
            return self.result('idle',reason='manual hold' if self.state.get('hold') else '6-hour cadence')
        if not prepare:
            return self.result('needs_prepare')
        try:
            built=self.io.build(self.state)
            if built is None:
                return self.result('idle',reason='All currently available Spotify episodes are completed')
            manifest,info=built
            release,created=self.io.ensure_release(manifest,info)
        except (QueueError,RuntimeError,OSError,ValueError,subprocess.SubprocessError) as exc:
            self.state['source_blocked']={'reason':str(exc)[:700],'at':iso(self.clock())}
            self.save('Keep His Story part queued while original media is unavailable')
            return self.result('source_blocked',reason=str(exc)[:700])
        self.adopt(release,info['releaseTag'],known_new=created)
        return self.reconcile()

    def block(self,reason):
        pending=self.state['pending']
        pending['phase']='blocked'
        pending['failure']={'reason':str(reason)[:700],'at':iso(self.clock())}
        self.save('Preserve rejected His Story attempt without automatic resubmission')
        return self.result('blocked',reason=str(reason)[:700])

    def validate_post(self,post):
        pending=self.state['pending']
        post_id=str(post.get('id') or '')
        require(re.fullmatch(r'[a-f0-9]{24}',post_id),'Lookup returned no valid Buffer post ID')
        require(not pending.get('postId') or post_id==pending['postId'],'Lookup returned a different Buffer post')
        require(str((post.get('channel') or {}).get('id'))==TARGET_CHANNEL_ID,
                'Lookup returned a different TikTok account')
        require(post.get('text')==pending['caption'],'Lookup returned a different caption')
        expected_backfill=(f'https://buffer-updates-media-backfill-bucket.s3.amazonaws.com/'
                           f'{BUFFER_ORG_ID}/{TARGET_CHANNEL_ID}/{post_id}_video.mp4')
        sources=[asset.get('source') for asset in post.get('assets',[]) if isinstance(asset,dict)]
        require(pending['videoUrl'] in sources or expected_backfill in sources,
                'Lookup did not verify the prepared video or its exact Buffer copy')
        return post_id

    def receipt(self):
        try:
            self.io.write_receipt(self.state['pending'])
        except (QueueError,OSError,ValueError,subprocess.SubprocessError) as exc:
            # The post ID was already saved in git; a release receipt is a second
            # recovery path and must not block advancement after a real send.
            print('Receipt warning:',str(exc)[:500],flush=True)

    def observe(self,post):
        try:
            post_id=self.validate_post(post)
        except QueueError as exc:
            return self.block(exc)
        pending=self.state['pending']
        pending['postId']=post_id
        status=str(post.get('status') or '').lower()
        error=post.get('error')
        if error or status in ('error','failed','rejected'):
            message=error.get('message') if isinstance(error,dict) else str(error or status)
            return self.block('TikTok/Buffer rejected this attempt: '+str(message))
        if status=='sent':
            link=urllib.parse.urlparse(str(post.get('externalLink') or ''))
            if not (link.scheme=='https' and link.hostname in ('tiktok.com','www.tiktok.com') and
                    re.fullmatch(r'/@rubaradaclips/video/\d+/?',link.path)):
                return self.block('Sent post has no verified Rubaradaclips TikTok video link')
            sent_at=parse_time(post.get('sentAt'))
            if not sent_at or sent_at.tzinfo is None:
                return self.block('Sent post has no verified timestamp')
            return self.advance(post,sent_at)
        pending['phase']=status if status in ('scheduled','sending') else 'accepted'
        pending['lastStatus']=status
        pending.pop('lastError',None)
        self.save('Save observed His Story Buffer post before waiting for delivery')
        self.receipt()
        return self.result('pending',postId=post_id,deliveryStatus=status)

    def reconcile(self):
        pending=self.state['pending']
        if pending.get('phase')=='blocked':
            return self.result('blocked',reason=(pending.get('failure') or {}).get('reason'))
        try:
            lookup=self.io.lookup(pending)
            require(lookup.get('ok') is True and lookup.get('videoUrl')==pending['videoUrl'],
                    'Publisher did not verify the current release video identity')
        except (APIError,QueueError) as exc:
            pending['lastError']=str(exc)[:700]
            self.save('Keep His Story pending while delivery status is unavailable')
            return self.result('pending',reason=str(exc)[:700])
        post=lookup.get('post')
        if post:
            return self.observe(post)
        if pending.get('postId'):
            return self.result('pending',reason='Known Buffer post is temporarily unavailable; do not recreate it')
        if not self.due():
            return self.result('pending',reason='Waiting for cadence or manual hold')
        if pending.get('phase') in ('submitting','submission_unknown'):
            previous=parse_time(pending.get('lastAbsentLookupAt'))
            if previous is None or self.clock()-previous>=ABSENT_INTERVAL:
                pending['absentLookups']=int(pending.get('absentLookups') or 0)+1
                pending['lastAbsentLookupAt']=iso(self.clock())
            submitted=parse_time(pending.get('submittedAt')) or self.clock()
            pending['phase']='submission_unknown'
            self.save('Reconcile uncertain His Story submission before any retry')
            if self.clock()-submitted<UNKNOWN_GRACE or pending['absentLookups']<2:
                return self.result('pending',reason='Waiting for two absent lookups and the submission visibility grace period')
        if not pending.get('verifiedSource'):
            return self.block('Legacy release can be reconciled but cannot create a new post without full original source proof')
        try:
            self.io.health()
        except (APIError,QueueError) as exc:
            pending['lastError']=str(exc)[:700]
            self.save('Keep prepared His Story part until its publisher is ready')
            return self.result('pending',reason=str(exc)[:700])
        pending.update({'phase':'submitting','submittedAt':iso(self.clock()),'absentLookups':0})
        pending.pop('lastAbsentLookupAt',None)
        self.save('Persist His Story submission intent before sending it to Buffer')
        try:
            result=self.io.publish(pending)
            require(result.get('ok') is True and re.fullmatch(r'[a-f0-9]{24}',str(result.get('postId') or '')),
                    'Publisher returned no verified Buffer identity')
            require(result.get('channelName')==TARGET_CHANNEL and result.get('channelId')==TARGET_CHANNEL_ID,
                    'Publisher returned a different TikTok target')
            require(result.get('videoUrl')==pending['videoUrl'],'Publisher returned a different video')
            pending.update({'postId':result['postId'],'phase':'accepted'})
            self.save('Save accepted His Story Buffer post ID before checking delivery')
            self.receipt()
            return self.result('pending',postId=pending['postId'])
        except APIError as exc:
            if exc.status in (400,401,403,422):
                return self.block('Publisher rejected this attempt: '+str(exc))
            pending['phase']='submission_unknown'
            pending['lastError']=str(exc)[:700]
            self.save('Preserve uncertain His Story create result for exact reconciliation')
            return self.result('pending',reason=str(exc)[:700])
        except QueueError as exc:
            return self.block(exc)

    def advance(self,post,sent_at):
        pending=self.state['pending']
        current=self.state.get('current') or {}
        key=pending['logicalPostKey']
        if self.state.get('last_logical_post_key')!=key:
            require(current.get('guid')==pending['guid'] and
                    int(current.get('next_part') or 0)==pending['part'],
                    'Refusing stale or out-of-order His Story advancement')
            if pending['part']>=pending['totalParts']:
                completed=list(self.state.get('completed') or [])
                if pending['guid'] not in completed:
                    completed.append(pending['guid'])
                self.state['completed']=completed
                next_episode=pending.get('nextEpisode')
                if next_episode and next_episode.get('guid') in completed:
                    next_episode=None
                # Persist completion even if RSS, Spotify, or the catalog is down.
                # A later preparation may refill a null current cursor.
                self.state['current']=next_episode
            else:
                self.state['current']={**current,'next_part':pending['part']+1}
            previous=parse_time(self.state.get('last_post_at'))
            self.state['last_post_at']=iso(max(previous,sent_at) if previous else sent_at)
            self.state['last_tiktok_link']=post['externalLink']
            self.state['last_buffer_post_id']=post['id']
            self.state['last_logical_post_key']=key
        self.state['last_verified_delivery']={
            'logicalPostKey':key,'releaseTag':pending['releaseTag'],'postId':post['id'],
            'channelId':TARGET_CHANNEL_ID,'videoUrl':pending['videoUrl'],
            'observedAssetUrls':[a.get('source') for a in post.get('assets',[]) if isinstance(a,dict)],
            'sentAt':post['sentAt'],'externalLink':post['externalLink']}
        self.state['pending']=None
        self.state.pop('source_blocked',None)
        self.save('Advance His Story queue after verified TikTok send')
        return self.result('sent',postId=post['id'],externalLink=post['externalLink'])


def main():
    parser=argparse.ArgumentParser(description='Durable Rubaradaclips generation-16 publisher')
    parser.add_argument('command',choices=('check','run'))
    parser.add_argument('--persist',action='store_true',help='Save state and source catalog in the production git repository')
    args=parser.parse_args()
    queue=DurableQueue(load_state(),RepositoryIO(persist=args.persist))
    result=queue.tick(prepare=args.command=='run')
    print(json.dumps(result,indent=2))
    output=os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output,'a') as file:
            file.write('allowed='+('true' if result['allowed'] else 'false')+'\n')
            file.write('pending='+('true' if result['pending'] else 'false')+'\n')
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a') as file:
            file.write('## Rubaradaclips His Story queue\n\n'+json.dumps(result,indent=2)+'\n\n')
    return 3 if result['status']=='source_blocked' else 2 if result['status']=='blocked' else 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except QueueError as exc:
        print(json.dumps({'ok':False,'error':str(exc)[:700]}),file=sys.stderr)
        raise SystemExit(2)


