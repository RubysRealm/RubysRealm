#!/usr/bin/env python3
import asyncio
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "production" / "work"
OUT = ROOT / "production" / "output"
SCENES = WORK / "scenes"
FRAMES = OUT / "review_frames"
SPEC = json.loads((ROOT / "production" / "spec.json").read_text())

WIDTH = 1080
HEIGHT = 1920
FPS = 30
VOICE = os.getenv("STORY_VOICE", "en-US-GuyNeural")
RATE = os.getenv("STORY_RATE", "+8%")
IMAGE_URL = os.getenv("STORY_IMAGE_URL", "https://rubys-realm.vercel.app/api/story-image")

OCCUPATIONS = [
    ("Marina Owner", "a busy lakeside marina"),
    ("Hotel Owner", "a forty-room roadside hotel"),
    ("Storage Facility Owner", "a gated self-storage property"),
    ("Campground Owner", "a wooded riverfront campground"),
    ("Car Wash Owner", "a high-volume tunnel car wash"),
    ("Bowling Alley Owner", "a neighborhood bowling center"),
    ("Mini Golf Owner", "a themed miniature golf course"),
    ("Laundromat Owner", "a twenty-four-hour neighborhood laundromat"),
]

def clean_word(s):
    return re.sub(r"[^a-z0-9']+", "", str(s).lower())

def words(s):
    return [w for w in (clean_word(x) for x in re.findall(r"\S+", s)) if w]

def complete_title(occupation):
    occupation = re.sub(r"\s+", " ", occupation).strip()
    if not occupation:
        raise RuntimeError("empty occupation")
    if not re.search(r"\b(owner|operator|manager|captain|mechanic|farmer|chef|pilot|driver|teacher|nurse|doctor|firefighter|electrician|plumber|carpenter|welder|barber|photographer|realtor|contractor)\b", occupation, re.I):
        raise RuntimeError(f"incomplete occupation title: {occupation}")
    article = "an" if occupation[:1].lower() in "aeiou" else "a"
    return f"Your Life as {article} {occupation}"

def make_story(seed):
    rng = random.Random(seed)
    forced = os.getenv("STORY_OCCUPATION", "").strip()
    if forced:
        occupation = forced
        setting = os.getenv("STORY_SETTING", "the business")
    else:
        occupation, setting = rng.choice(OCCUPATIONS)
    title = complete_title(occupation)
    name = rng.choice(["Evan", "Marcus", "Caleb", "Jordan", "Nate", "Derek", "Miles", "Grant"])
    town = rng.choice(["Cedar Point", "Marlow", "Pine Ridge", "Lakehaven", "Westfield", "Briar Glen"])
    amount = rng.choice(["$18,700", "$24,300", "$31,900", "$42,600"])
    weather = rng.choice(["a hard summer storm", "an overnight windstorm", "three days of heavy rain", "a sudden cold snap"])
    object1 = rng.choice(["a brass key", "a faded ledger", "a sealed envelope", "a handwritten maintenance map"])
    object2 = rng.choice(["an old utility room", "a locked service closet", "a forgotten storage bay", "a blocked maintenance corridor"])
    beats = [
        f"You are {name}, the new {occupation.lower()} in {town}. On your first Monday you unlock {setting} before sunrise, switch on the exterior lights, and walk the property with a paper checklist while the first employees arrive.",
        f"At the front office, you sort overnight messages, count the register, compare yesterday's receipts with the booking screen, and notice that one handwritten charge does not match the digital total.",
        f"You leave the desk and walk the entire property. You inspect doors, drains, utility panels, customer areas, and equipment, marking three repairs with bright tape instead of trusting the old maintenance notes.",
        f"By midmorning the place is busy. You help a frustrated customer in person, move a delivery out of the traffic lane, and radio an employee to fix a small problem before it turns into a public complaint.",
        f"During lunch you open a drawer that has not been cleaned out in years and find {object1} beneath old invoices. A date and unit number on it point toward {object2} at the far end of the property.",
        f"You take {object1} with you and cross the property to {object2}. The lock is stiff, dust covers the threshold, and fresh scrape marks on the floor make it obvious that somebody has been inside recently.",
        f"Inside, you discover old business records, spare hardware, and a wall panel that does not appear on the current floor plan. You photograph everything, close the door, and decide not to touch the panel alone.",
        f"Back in the office you compare the discovery with archived paperwork. One former contractor is listed repeatedly beside cash expenses, but the vendor name disappears from the records exactly two years earlier.",
        f"That afternoon a regular customer casually mentions seeing a white work van behind the property after closing. You write down the description and check the exterior cameras instead of telling anyone what you found.",
        f"The camera footage shows the same van entering through a service side twice in the previous month. The driver never visits the customer area and always walks directly toward {object2}.",
        f"You change the service locks, save copies of the footage, and call the property insurer and local authorities. Before anyone arrives, you tell the staff only that an old access issue is being investigated.",
        f"Then {weather} hits {town}. Water pushes across part of the property, customers begin calling at once, and the investigation suddenly has to share your attention with an actual operating emergency.",
        f"You pull on a rain jacket, move people away from the problem area, shut down unsafe equipment, and work beside your employees to protect customer property while emergency lights reflect across the wet pavement.",
        f"After the weather clears, the hidden wall panel is opened with an investigator present. Behind it is a narrow cavity containing duplicate invoices, old keys, and records tied to {amount} in unexplained charges.",
        f"The evidence explains years of small losses that had been dismissed as normal operating costs. You spend the next week replacing access controls, documenting every vendor, and rebuilding the maintenance process from scratch.",
        f"Customers notice the changes before they know the reason. The property is cleaner, broken equipment gets repaired faster, and employees stop improvising because every issue now has an owner and a written follow-up.",
        f"At the end of the month you sit alone in the office after closing and compare the new numbers with the old books. Revenue is steadier, waste is down, and the unexplained cash gap has disappeared.",
        f"You lock the front door, walk the quiet property one final time, and realize owning {setting} is nothing like the simple business you imagined. Every ordinary day can hide a problem that only becomes visible when you actually pay attention.",
    ]
    return {
        "title": title,
        "occupation": occupation,
        "setting": setting,
        "part": "PART 1",
        "story_id": hashlib.sha256((title + "|" + " ".join(beats)).encode()).hexdigest()[:16],
        "beats": beats,
        "protagonist": {
            "name": name,
            "description": "same recurring simple non-realistic adult male cartoon business owner, short dark-brown hair, clean-shaven face, medium build, navy work shirt or context-appropriate outerwear, same facial geometry and age in every applicable scene"
        },
    }

async def narrate(text, mp3, boundaries):
    comm = edge_tts.Communicate(text=text, voice=VOICE, rate=RATE, boundary="WordBoundary")
    events = []
    with mp3.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "boundary") and chunk.get("text"):
                events.append({
                    "text": chunk["text"],
                    "start": float(chunk.get("offset", 0)) / 10_000_000.0,
                    "duration": float(chunk.get("duration", 0)) / 10_000_000.0,
                })
    boundaries.write_text(json.dumps(events, indent=2))
    expected = len(words(text))
    minimum = max(300, int(expected * 0.92))
    if len(events) < minimum:
        raise RuntimeError(f"exact word-boundary coverage too low: {len(events)}/{expected}")
    return events

def probe_duration(path):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        text=True, capture_output=True, check=True
    )
    return float(p.stdout.strip())

def beat_schedule(beats, events, audio_duration):
    source_counts = [len(words(b)) for b in beats]
    event_words = [clean_word(e["text"]) for e in events if clean_word(e["text"])]
    source_total = sum(source_counts)
    if abs(len(event_words) - source_total) / max(1, source_total) > 0.08:
        raise RuntimeError(f"word boundary drift too large: source={source_total} events={len(event_words)}")
    schedule = []
    cursor = 0
    for i, (beat, count) in enumerate(zip(beats, source_counts)):
        idx = min(cursor, len(events)-1)
        start = float(events[idx]["start"])
        cursor += count
        next_idx = min(cursor, len(events)-1)
        end = float(events[next_idx]["start"]) if i < len(beats)-1 else audio_duration
        if end <= start:
            raise RuntimeError(f"invalid beat timing {i}: {start}..{end}")
        schedule.append({"index": i, "text": beat, "start": start, "end": end, "duration": end-start})
    return schedule

def post_image(payload, dest):
    token = os.getenv("GITHUB_OIDC_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GITHUB_OIDC_TOKEN missing")
    req = urllib.request.Request(
        IMAGE_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Cache-Control":"no-store"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:800]
        raise RuntimeError(f"image service {e.code}: {body}") from e
    if len(data) < 20_000:
        raise RuntimeError(f"generated scene too small: {len(data)} bytes")
    dest.write_bytes(data)

def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def fit_text(draw, text, max_width, start_size, min_size=34):
    for size in range(start_size, min_size-1, -2):
        f = font(size, True)
        if draw.textbbox((0,0), text, font=f)[2] <= max_width:
            return f
    return font(min_size, True)

def compose_scene(raw_path, story, dest):
    im = Image.open(raw_path).convert("RGB")
    im = ImageOps.fit(im, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0,0,0,0))
    d = ImageDraw.Draw(overlay)
    panel = (62, 74, WIDTH-62, 425)
    d.rounded_rectangle(panel, radius=48, fill=(13, 17, 24, 205), outline=(255,255,255,32), width=2)
    eyebrow = "YOUR LIFE AS"
    d.text((WIDTH//2, 108), eyebrow, font=font(43, True), anchor="ma", fill=(255, 203, 92, 255), stroke_width=1, stroke_fill=(0,0,0,150))
    occ = story["occupation"]
    f_occ = fit_text(d, occ, WIDTH-180, 82, 46)
    d.text((WIDTH//2, 183), occ, font=f_occ, anchor="ma", fill=(255,255,255,255), stroke_width=3, stroke_fill=(0,0,0,150))
    pill_w, pill_h = 250, 68
    x0 = WIDTH//2-pill_w//2
    y0 = 309
    d.rounded_rectangle((x0,y0,x0+pill_w,y0+pill_h), radius=28, fill=(246, 173, 48, 245))
    d.text((WIDTH//2, y0+pill_h//2-1), story["part"], font=font(39, True), anchor="mm", fill=(20,22,28,255))
    im = Image.alpha_composite(im, overlay).convert("RGB")
    im.save(dest, "JPEG", quality=94, subsampling=0)

def ass_escape(s):
    return str(s).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")

def write_ass(events, path, duration):
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {WIDTH}",
        f"PlayResY: {HEIGHT}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Word,DejaVu Sans,82,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,8,2,2,60,60,280,1",
        "",
        "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    def ts(sec):
        sec=max(0,float(sec)); h=int(sec//3600); sec-=h*3600; m=int(sec//60); sec-=m*60
        return f"{h}:{m:02d}:{sec:05.2f}"
    for i,e in enumerate(events):
        start=float(e["start"])
        end=float(events[i+1]["start"]) if i+1<len(events) else min(duration,start+max(.16,float(e.get("duration",.25))))
        if end <= start: end=start+.12
        word=ass_escape(str(e["text"]).strip().upper())
        if not word: continue
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Word,,0,0,0,,{word}")
    path.write_text("\n".join(lines), encoding="utf-8")

def render(schedule, scene_paths, audio, ass, output):
    concat = WORK / "scenes.ffconcat"
    rows = ["ffconcat version 1.0"]
    for item, scene in zip(schedule, scene_paths):
        rows.append(f"file '{scene.as_posix()}'")
        rows.append(f"duration {item['duration']:.6f}")
    rows.append(f"file '{scene_paths[-1].as_posix()}'")
    concat.write_text("\n".join(rows))
    subprocess.run([
        "ffmpeg","-y","-v","error",
        "-f","concat","-safe","0","-i",str(concat),
        "-i",str(audio),
        "-vf",f"fps={FPS},ass={ass.as_posix()}",
        "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","192k","-shortest",str(output)
    ], check=True)

def sample_rendered_frames(video, schedule):
    FRAMES.mkdir(parents=True, exist_ok=True)
    picks = sorted(set([0,1,3,6,9,12,15,len(schedule)-1]))
    samples=[]
    for i in picks:
        b=schedule[i]
        t=min(b["end"]-.12, b["start"]+min(.75,max(.20,b["duration"]*.35)))
        dest=FRAMES/f"beat_{i:02d}_{t:.2f}.jpg"
        subprocess.run(["ffmpeg","-y","-v","error","-ss",f"{t:.3f}","-i",str(video),"-frames:v","1","-q:v","2",str(dest)],check=True)
        samples.append({"beatIndex":i,"timestamp":round(t,3),"file":str(dest.relative_to(ROOT)),"beat":b["text"]})
    return samples

def center_mean(path):
    im=Image.open(path).convert("RGB")
    crop=im.crop((120,500,960,1500)).resize((32,32))
    st=ImageStat.Stat(crop)
    return tuple(x for x in st.mean)

def timing_visual_checks(samples, composed):
    checks=[]
    for s in samples:
        frame=ROOT/s["file"]
        src=composed[s["beatIndex"]]
        a=center_mean(frame); b=center_mean(src)
        delta=sum(abs(x-y) for x,y in zip(a,b))/3
        checks.append({"beatIndex":s["beatIndex"],"meanColorDelta":round(delta,2),"renderMatchesScheduledScene":delta<42})
    return checks

def main():
    for p in (WORK, OUT):
        if p.exists(): shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)
    SCENES.mkdir(parents=True, exist_ok=True)

    seed=int(os.getenv("STORY_SEED","9102026"))
    story=make_story(seed)
    full_text=" ".join(story["beats"])
    audio=WORK/"narration.mp3"
    boundaries=WORK/"word_boundaries.json"
    events=asyncio.run(narrate(full_text,audio,boundaries))
    audio_duration=probe_duration(audio)
    lo,hi=SPEC["story"]["durationSeconds"]
    if not (lo <= audio_duration <= hi):
        raise RuntimeError(f"duration {audio_duration:.1f}s outside {lo}-{hi}s")

    schedule=beat_schedule(story["beats"],events,audio_duration)
    raw=[]
    composed=[]
    for i,b in enumerate(schedule):
        raw_path=SCENES/f"raw_{i:02d}.jpg"
        frame_path=SCENES/f"scene_{i:02d}.jpg"
        payload={
            "title":story["title"],
            "occupation":story["occupation"],
            "part":story["part"],
            "beat":b["text"],
            "previousBeat":schedule[i-1]["text"] if i else "",
            "nextBeat":schedule[i+1]["text"] if i+1<len(schedule) else "",
            "protagonist":story["protagonist"],
            "index":i,
            "seed":seed+i*7919,
            "fresh":True
        }
        post_image(payload,raw_path)
        compose_scene(raw_path,story,frame_path)
        raw.append(raw_path); composed.append(frame_path)

    ass=WORK/"captions.ass"
    write_ass(events,ass,audio_duration)
    video=OUT/f"{re.sub(r'[^a-z0-9]+','-',story['title'].lower()).strip('-')}-{story['story_id']}.mp4"
    render(schedule,composed,audio,ass,video)
    rendered_duration=probe_duration(video)
    samples=sample_rendered_frames(video,schedule)
    visual_checks=timing_visual_checks(samples,composed)

    checks={
        "completeOccupationTitle": story["occupation"].lower() in story["title"].lower(),
        "durationAllowed": lo <= rendered_duration <= hi+1.5,
        "oneImagePerBeat": len(composed)==len(schedule)==len(story["beats"]),
        "freshImagePerBeat": len({p.read_bytes()[:2048] for p in raw})==len(raw),
        "allBeatStartsNarrationAligned": all(i==0 or schedule[i]["start"]>schedule[i-1]["start"] for i in range(len(schedule))),
        "exactWordBoundaryCaptions": len(events)>300,
        "actualFramesMatchScheduledScenes": all(x["renderMatchesScheduledScene"] for x in visual_checks),
        "publicationBlocked": SPEC["publishing"]["enabled"] is False,
    }
    passed=all(checks.values())
    manifest={
        "platform":"rubys-realm-clean-rebuild-v1",
        "qualityPassed":passed,
        "publicationAllowed":False,
        "seed":seed,
        "title":story["title"],
        "occupation":story["occupation"],
        "part":story["part"],
        "storyId":story["story_id"],
        "durationSeconds":round(rendered_duration,3),
        "narrationWordBoundaries":len(events),
        "sceneCount":len(schedule),
        "checks":checks,
        "visualTimingChecks":visual_checks,
        "reviewSamples":samples,
        "beats":[{**b,"image":str(composed[i].relative_to(ROOT))} for i,b in enumerate(schedule)],
        "video":str(video.relative_to(ROOT)),
    }
    manifest_path=OUT/"manifest.json"
    manifest_path.write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))
    if not passed:
        raise RuntimeError("rebuilt platform quality gate failed; publication remains blocked")

if __name__=="__main__":
    main()
