#!/usr/bin/env python3
"""Reliable Rubarataclips / Snook queue: public RSS audio -> vertical video.

Use 'check', 'build', and 'advance' as separate, failure-safe workflow phases.
The queue only advances after Buffer confirms the post was sent to TikTok.
"""
import hashlib
import json
import math
import re
import subprocess
import sys
import textwrap
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED = "https://feeds.megaphone.fm/QCD5686868811"
SPOTIFY_SHOW = "https://open.spotify.com/show/2FH70nnKmpdV5PY0fp4F9Q"
START_SPOTIFY_EPISODE = "https://open.spotify.com/episode/3mh1biAkuwBmDwRnSxSy0U"
START_GUID = "d7dc8ad1-0e92-483a-9da2-376fd2c885a1"
START_TITLE = "10 Unspeakable TRUE Scary Stories"
BASE = Path("rubyclips")
STATE_PATH = BASE / "snook_rss_state.json"
WORK = BASE / "snook_work"
OUT = BASE / "snook_output"
PART_SECONDS = 180
POST_HOURS = 6
GENERATION = 10
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
TARGET = "rubaradaclips"

def run(args, timeout=900):
    print("+", " ".join(str(s) for s in args), flush=True)
    subprocess.run(args, check=True, timeout=timeout)

def media_info(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
    ], text=True, timeout=90))

def now():
    return datetime.now(timezone.utc)

def parse_time(s):
    if not s: return None
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError: return None

def iso(t):
    return t.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def safe_text(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()

def normalized(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())

def series_id(guid):
    return "snook-" + hashlib.sha256(guid.encode()).hexdigest()[:16]

def download(url, filename, min_size=10000):
    req = urllib.request.Request(url, headers={
        "User-Agent":"Mozilla/5.0 (compatible; Rubarataclips/1.0)",
        "Accept":"*/*"
    })
    with urllib.request.urlopen(req,timeout=90) as response:
        filename.write_bytes(response.read())
    if filename.stat().st_size < min_size: raise RuntimeError("Source file too small")

def duration_value(v):
    text = safe_text(v)
    if text.isdigit(): return float(text)
    if ":" in text:
        parts = text.split(":")
        try:
            n=0
            for p in parts: n = n*60 + float(p)
            return n
        except ValueError: pass
    return 0.0

def get_feed():
    req=urllib.request.Request(FEED,headers={
        "User-Agent":"Mozilla/5.0 (compatible; Rubarataclips/1.0)",
        "Accept":"application/rss+xml,application/xml,*/*"
    })
    with urllib.request.urlopen(req,timeout=90) as resp:
        xml=resp.read()
    root=ET.fromstring(xml)
    entries=[]
    for node in root.findall("./channel/item"):
        guid=safe_text(node.findtext("guid"))
        enc=node.find("enclosure")
        if not guid or enc is None: continue
        audio_url=enc.attrib.get("url","")
        mime=enc.attrib.get("type","")
        if not audio_url.startswith("https://") or mime not in ("audio/mpeg", "audio/mp3"):
            continue
        date_raw=node.findtext("pubDate") or ""
        try: date=parsedate_to_datetime(date_raw).astimezone(timezone.utc)
        except: continue
        cover_node=node.find(ITUNES+"image")
        cover=cover_node.attrib.get("href","") if cover_node is not None else ""
        entries.append({
            "guid": guid, "title": safe_text(node.findtext("title")),
            "date": iso(date),
            "audioUrl":audio_url,
            "mediaType":mime,
            "duration":duration_value(node.findtext(ITUNES+"duration")),
            "coverUrl":cover,
        })
    entries.sort(key=lambda e:(e["date"],e["guid"]))
    if len(entries)<10: raise RuntimeError("Public Snook RSS returned too few episodes")
    start=next((i for i,e in enumerate(entries) if e["guid"]==START_GUID),None)
    if start is None: raise RuntimeError("Requested starting Spotify episode missing from official RSS")
    if normalized(entries[start]["title"])!=normalized(START_TITLE):
        raise RuntimeError("Official feed episode GUID/title changed unexpectedly")
    return entries, start

def load_state():
    if not STATE_PATH.exists(): raise RuntimeError("Missing durable Snook RSS state file")
    state=json.loads(STATE_PATH.read_text())
    if state.get("feed")!=FEED or state.get("startGuid")!=START_GUID:
        raise RuntimeError("State points to wrong podcast source")
    return state

def selected(state, entries, start):
    completed=set(state.get("completedGuids") or [])
    visible=entries[start:]
    current=state.get("currentGuid") or next((e["guid"] for e in visible if e["guid"] not in completed),None)
    if not current: return None
    if current in completed: raise RuntimeError("Current episode already marked complete")
    chosen=next((e for e in visible if e["guid"]==current),None)
    if chosen is None: raise RuntimeError("Current episode missing from feed; refusing to skip")
    if int(state.get("nextPart") or 0)<1: raise RuntimeError("Invalid part counter")
    return chosen

def check():
    state=load_state()
    entries,start=get_feed()
    current=selected(state,entries,start)
    allowed=bool(current)
    reason="ready"
    last=parse_time(state.get("lastPostAt"))
    if last and now()-last < timedelta(hours=POST_HOURS):
        allowed=False
        reason="6-hour cadence"
    if state.get("hold"):
        allowed=False
        reason="manual hold"
    print(json.dumps({
        "allowed":allowed, "reason":reason,
        "episodesInFeed":len(entries), "startPosition":start+1,
        "current":current["title"] if current else None,
        "part":state.get("nextPart"),
        "lastPostAt":state.get("lastPostAt"),
    },indent=2))
    output_path=__import__("os").environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path,"a") as f:
            f.write("allowed="+("true" if allowed else "false")+"\n")
    return allowed

def build():
    state=load_state()
    entries,startidx=get_feed()
    episode=selected(state,entries,startidx)
    if not episode: raise RuntimeError("No more Snook episodes to publish")
    if episode["duration"]<30: raise RuntimeError("RSS does not expose full episode duration")
    part=int(state["nextPart"])
    total=math.ceil(episode["duration"]/PART_SECONDS)
    if part>total: raise RuntimeError("Part counter beyond end of episode")
    start=(part-1)*PART_SECONDS
    seconds=min(PART_SECONDS,episode["duration"]-start)
    if seconds<10: raise RuntimeError("Refusing tiny remainder")

    WORK.mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
    for p in WORK.glob("*"):
        if p.is_file(): p.unlink()
    for p in OUT.glob("*"):
        if p.is_file(): p.unlink()

    # Full-length original narration is served by the show's public Megaphone RSS,
    # avoiding encrypted Spotify video and YouTube scraping altogether.
    clip=WORK/"segment.m4a"
    source_options=[
        episode["audioUrl"],
        re.search(r"https://traffic\.megaphone\.fm/[^?&\s]+\.mp3",episode["audioUrl"]).group(0)
        if re.search(r"https://traffic\.megaphone\.fm/[^?&\s]+\.mp3",episode["audioUrl"])
        else None,
    ]
    problems=[]
    for url in filter(None,source_options):
        try:
            run(["ffmpeg","-hide_banner","-v","error","-y",
                 "-rw_timeout","60000000",
                 "-ss",f"{start:.3f}","-i",url,"-t",f"{seconds:.3f}",
                 "-vn","-ac","2","-ar","48000","-c:a","aac","-b:a","160k",str(clip)],timeout=480)
            a=media_info(clip)
            adur=float(a["format"]["duration"])
            if not (seconds-4 <= adur <= seconds+2):
                raise RuntimeError(f"Audio segment duration mismatch: {adur:.2f}")
            break
        except Exception as exc:
            problems.append(str(exc))
            clip.unlink(missing_ok=True)
    if not clip.exists(): raise RuntimeError("RSS audio segment unavailable: "+"; ".join(problems))

    cover=WORK/"cover.jpg"
    for url in [episode.get("coverUrl"),"https://megaphone.imgix.net/podcasts/754870e0-2781-11f1-8813-a3900e24e7d9/image/31609ffb14df0e68c0eb78702c9306b8.jpg"]:
        if not url: continue
        try:
            download(url,cover,1000)
            break
        except Exception as exc:
            print("Artwork URL failed:",exc)
            cover.unlink(missing_ok=True)

    title=WORK/"title.txt"
    title.write_text("\n".join(textwrap.wrap(episode["title"].upper(),width=31)[:3]),encoding="utf-8")
    label=WORK/"part.txt"
    label.write_text(f"PART {part} OF {total}",encoding="utf-8")
    background=WORK/"background.png"
    if cover.exists():
        filter_complex=(
            "[0:v]split=2[back][front];"
            "[back]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,gblur=sigma=27,eq=brightness=-0.20[bg];"
            "[front]scale=800:820:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:680,drawbox=x=45:y=135:w=990:h=430:color=black@0.80:t=fill,"
            f"drawtext=fontfile={FONT}:textfile={title.as_posix()}:fontcolor=white:fontsize=46:"
            "line_spacing=16:x=(w-text_w)/2:y=185,"
            f"drawtext=fontfile={FONT}:textfile={label.as_posix()}:fontcolor=white:fontsize=42:"
            "x=(w-text_w)/2:y=475,format=rgb24[out]"
        )
        run(["ffmpeg","-y","-hide_banner","-v","error","-i",str(cover),
             "-filter_complex",filter_complex,"-map","[out]","-frames:v","1",
             str(background)],timeout=90)
    else:
        filter_complex=(
            "drawbox=x=45:y=135:w=990:h=430:color=black@0.85:t=fill,"
            f"drawtext=fontfile={FONT}:textfile={title.as_posix()}:fontcolor=white:fontsize=46:"
            "line_spacing=16:x=(w-text_w)/2:y=185,"
            f"drawtext=fontfile={FONT}:textfile={label.as_posix()}:fontcolor=white:fontsize=42:"
            "x=(w-text_w)/2:y=475,format=rgb24"
        )
        run(["ffmpeg","-y","-hide_banner","-v","error",
             "-f","lavfi","-i","color=c=0x15151c:s=1080x1920:r=1",
             "-vf",filter_complex,"-frames:v","1",str(background)],timeout=90)

    id_=series_id(episode["guid"])
    filename=f"snook-{id_}-r{GENERATION}-part-{part:02d}.mp4"
    output_video=OUT/filename
    render_filter=(
        "[1:a]asplit=2[audio][vis];"
        "[vis]showwaves=s=880x140:mode=cline:colors=white:rate=24[wave];"
        "[0:v][wave]overlay=(W-w)/2:1560:shortest=1,format=yuv420p[vout]"
    )
    run(["ffmpeg","-y","-hide_banner","-v","error","-loop","1","-framerate","24",
         "-i",str(background),"-i",str(clip),
         "-filter_complex",render_filter,"-map","[vout]","-map","[audio]",
         "-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p",
         "-r","24","-c:a","aac","-b:a","160k","-ar","48000",
         "-t",f"{seconds:.3f}","-movflags","+faststart","-shortest",str(output_video)],timeout=1200)
    info=media_info(output_video)
    vids=[s for s in info["streams"] if s["codec_type"]=="video"]
    auds=[s for s in info["streams"] if s["codec_type"]=="audio"]
    dur=float(info["format"]["duration"])
    if len(vids)!=1 or len(auds)!=1: raise RuntimeError("Missing final audio or video")
    if vids[0]["codec_name"]!="h264" or auds[0]["codec_name"]!="aac":
        raise RuntimeError("Wrong TikTok media codecs")
    if (vids[0]["width"],vids[0]["height"])!=(1080,1920):
        raise RuntimeError("Video is not full vertical resolution")
    if not (seconds-4<=dur<=seconds+2) or output_video.stat().st_size<100000:
        raise RuntimeError("Final MP4 duration/size invalid")
    audio_dur=float(auds[0].get("duration") or dur)
    if abs(audio_dur-dur)>2: raise RuntimeError("Audio/video duration mismatch")

    title_tag=re.sub(r"[^A-Za-z0-9]","",episode["title"])[:38]
    story_hashtag="#"+(title_tag if title_tag else "SnookStories")
    caption=f'{episode["title"]} — Part {part} of {total} {story_hashtag} #ScaryStories #rubaradaclips'
    logical=f"rubyclips:{id_}:r{GENERATION}:p{part}"
    tag=f"rubyclips-tt-{id_}-r{GENERATION}-p{part}"
    manifest={
        "platform":"rubyclips-tiktok-story-v1",
        "pipelineRevision":"avsync-v4-direct-builder",
        "sourceProvider":"snook-podcast-rss",
        "sourceChannel":"snook",
        "sourceSeriesId":id_,
        "sourceSeriesTitle":episode["title"],
        "sourceVideoIds":[episode["guid"]],
        "sourceUrls":[FEED],
        "sourceEpisodeGuid":episode["guid"],
        "sourceMediaType":"audio/mpeg",
        "spotifyShowUrl":SPOTIFY_SHOW,
        "requestedStartEpisodeUrl":START_SPOTIFY_EPISODE,
        "restartGeneration":GENERATION,
        "logicalPostKey":logical,
        "segmentIndex":part,
        "segmentTotal":total,
        "segmentDurationSeconds":round(dur,3),
        "file":filename,
        "targetChannel":TARGET,
        "caption":caption,
        "storyHashtag":story_hashtag,
        "titleBurnedIn":True,
        "partLabelBurnedIn":True,
        "coverArtEmbedded":cover.exists(),
        "visualMode":"animated-audio-waveform-with-podcast-art",
        "coverTitleBurnedIn":True,
        "thumbnailOffsetMs":1000,
    }
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    info_record={
        "guid":episode["guid"],"title":episode["title"],"episodeDate":episode["date"],
        "part":part,"totalParts":total,"sourceSeconds":episode["duration"],
        "startSeconds":start,"endSeconds":start+seconds,
        "duration":round(dur,3),"logicalPostKey":logical,"releaseTag":tag,
    }
    (OUT/"part-info.json").write_text(json.dumps(info_record,indent=2)+"\n")
    print(json.dumps({"ok":True,"file":str(output_video),"bytes":output_video.stat().st_size,
        "duration":dur,"tag":tag,"partInfo":info_record,"manifest":manifest},indent=2))

def advance(sent_file):
    state=load_state()
    info=json.loads((OUT/"part-info.json").read_text())
    sent=json.loads(Path(sent_file).read_text())
    post=sent.get("post") or {}
    if sent.get("ok") is not True or post.get("status")!="sent":
        raise RuntimeError("Cannot advance without confirmed Buffer sent status")
    if str((post.get("channel") or {}).get("id"))!="6a9f6ff1cd8b9c702c2897e1":
        raise RuntimeError("Wrong TikTok channel")
    link=str(post.get("externalLink") or "")
    if "tiktok.com/@rubaradaclips/video/" not in link:
        raise RuntimeError("TikTok video link not confirmed")
    sent_at=str(post.get("sentAt") or "")
    if not parse_time(sent_at): raise RuntimeError("TikTok sentAt missing")
    if state.get("currentGuid")!=info["guid"] or int(state.get("nextPart",0))!=int(info["part"]):
        if state.get("lastLogicalPostKey")==info["logicalPostKey"]:
            print("Already committed part",info["logicalPostKey"])
            return
        raise RuntimeError("Refusing stale or out-of-order queue advance")

    state["lastPostAt"]=sent_at
    state["lastTiktokLink"]=link
    state["lastBufferPostId"]=post.get("id")
    state["lastLogicalPostKey"]=info["logicalPostKey"]
    state["lastPostedPart"]=int(info["part"])
    if int(info["part"])>=int(info["totalParts"]):
        done=list(state.get("completedGuids") or [])
        if info["guid"] not in done:done.append(info["guid"])
        state["completedGuids"]=done
        entries,startidx=get_feed()
        eligible=[e for e in entries[startidx:] if e["guid"] not in done]
        state["currentGuid"]=eligible[0]["guid"] if eligible else None
        state["nextPart"]=1
    else:
        state["nextPart"]=int(info["part"])+1
    state["lastConfirmedEpisodeTitle"]=info["title"]
    STATE_PATH.write_text(json.dumps(state,indent=2)+"\n")
    print(json.dumps({"advanced":True,"lastSent":sent_at,"tiktok":link,
                      "nextGuid":state.get("currentGuid"),"nextPart":state["nextPart"]},indent=2))

if __name__=="__main__":
    if len(sys.argv)<2: raise SystemExit("Usage: snook_rss_pipeline.py check|build|advance [status.json]")
    if sys.argv[1]=="check":check()
    elif sys.argv[1]=="build":build()
    elif sys.argv[1]=="advance":advance(sys.argv[2])
    else:raise SystemExit("Invalid command")
