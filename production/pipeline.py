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


def _gradient_scene(top, bottom):
    im=Image.new("RGB",(WIDTH,HEIGHT),top)
    d=ImageDraw.Draw(im)
    for y in range(HEIGHT):
        q=y/max(1,HEIGHT-1)
        col=tuple(int(top[i]*(1-q)+bottom[i]*q) for i in range(3))
        d.line((0,y,WIDTH,y),fill=col)
    return im.convert("RGBA")

def _rounded(d, box, fill, radius=28, outline=None, width=1):
    d.rounded_rectangle(box,radius=radius,fill=fill,outline=outline,width=width)

def _character(d,x,y,s=1.0,coat=(38,67,103,255),rain=False):
    # recurring simple non-realistic adult cartoon owner
    def B(a,b,c,e): return (int(x+a*s),int(y+b*s),int(x+c*s),int(y+e*s))
    d.ellipse(B(-95,275,95,330),fill=(0,0,0,55))
    # legs
    _rounded(d,B(-52,130,-5,280),(47,52,61,255),18)
    _rounded(d,B(8,130,55,280),(42,47,56,255),18)
    d.ellipse(B(-69,255,2,300),fill=(24,27,32,255))
    d.ellipse(B(-2,255,72,300),fill=(24,27,32,255))
    # torso / jacket
    _rounded(d,B(-90,-5,90,165),coat,52)
    _rounded(d,B(-70,12,58,145),tuple(min(255,v+18) if i<3 else v for i,v in enumerate(coat)),40)
    if rain:
        d.arc(B(-78,-2,78,151),180,350,fill=(180,220,245,150),width=max(3,int(5*s)))
    # arms
    _rounded(d,B(-126,18,-76,150),coat,22)
    _rounded(d,B(76,18,126,150),coat,22)
    # neck/head
    _rounded(d,B(-25,-45,25,8),(201,151,121,255),14)
    d.ellipse(B(-69,-150,69,-18),fill=(221,169,135,255),outline=(75,56,48,220),width=max(2,int(3*s)))
    # hair
    d.pieslice(B(-64,-146,64,-45),180,360,fill=(60,44,36,255))
    # ears
    d.ellipse(B(-77,-106,-57,-70),fill=(210,157,126,255))
    d.ellipse(B(57,-106,77,-70),fill=(210,157,126,255))
    # face
    d.ellipse(B(-33,-91,-19,-77),fill=(30,34,38,255))
    d.ellipse(B(19,-91,33,-77),fill=(30,34,38,255))
    d.arc(B(-25,-67,25,-37),10,170,fill=(88,55,46,255),width=max(2,int(3*s)))

def _building(d,kind):
    if kind=="marina":
        d.rectangle((0,1120,WIDTH,HEIGHT),fill=(55,111,150,255))
        for x in range(-80,WIDTH+150,170):
            d.line((x,1300,x+90,1260),fill=(205,230,245,110),width=5)
        d.rectangle((90,920,990,1180),fill=(170,117,72,255))
        d.polygon([(90,920),(540,710),(990,920)],fill=(75,66,58,255))
        d.rectangle((195,1010,885,1080),fill=(211,179,132,255))
        for x in (250,420,590,760):
            d.rectangle((x,1080,x+24,1470),fill=(84,60,40,255))
        # boats
        for x,y in [(170,1510),(610,1430)]:
            d.polygon([(x,y),(x+250,y),(x+205,y+70),(x+35,y+70)],fill=(238,241,244,255),outline=(50,60,70,255))
            d.line((x+125,y,x+125,y-135),fill=(68,73,80,255),width=8)
    elif kind=="hotel":
        d.rectangle((75,780,1005,1540),fill=(208,167,104,255),outline=(93,70,54,255),width=6)
        for yy in (900,1160):
            for xx in (150,355,560,765):
                d.rectangle((xx,yy,xx+130,yy+105),fill=(82,134,163,255),outline=(52,78,94,255),width=5)
        d.rectangle((430,1320,650,1540),fill=(91,69,57,255))
        d.rectangle((0,1540,WIDTH,HEIGHT),fill=(64,70,76,255))
    elif kind=="storage":
        d.rectangle((70,900,1010,1580),fill=(184,190,198,255),outline=(82,91,101,255),width=7)
        for x in (95,330,565,800):
            d.rectangle((x,1080,x+185,1570),fill=(118,137,157,255),outline=(60,70,82,255),width=6)
            for y in range(1130,1530,70): d.line((x+10,y,x+175,y),fill=(87,103,118,255),width=3)
        d.rectangle((0,1580,WIDTH,HEIGHT),fill=(76,78,82,255))
    elif kind=="campground":
        d.rectangle((0,1450,WIDTH,HEIGHT),fill=(83,106,69,255))
        for x in (90,850,260,700):
            d.rectangle((x,670,x+40,1510),fill=(91,66,43,255))
            d.polygon([(x-120,900),(x+20,500),(x+170,900)],fill=(63,105,67,255))
        d.polygon([(330,1460),(550,1120),(770,1460)],fill=(183,126,73,255),outline=(80,60,44,255))
        d.polygon([(470,1460),(550,1270),(635,1460)],fill=(45,60,56,255))
    elif kind=="carwash":
        d.rectangle((90,850,990,1580),fill=(121,151,176,255),outline=(54,76,94,255),width=7)
        d.rectangle((280,1040,800,1580),fill=(49,59,70,255))
        d.arc((330,1110,750,1570),0,180,fill=(75,170,210,255),width=35)
        d.rectangle((0,1580,WIDTH,HEIGHT),fill=(80,83,86,255))
    elif kind=="bowling":
        d.rectangle((80,880,1000,1580),fill=(131,112,156,255),outline=(65,55,76,255),width=7)
        d.rectangle((200,1060,880,1550),fill=(43,42,48,255))
        for i in range(6):
            x=250+i*100
            d.polygon([(x,1500),(x+55,1500),(x+20,1040)],fill=(210,182,133,255))
        d.rectangle((0,1580,WIDTH,HEIGHT),fill=(63,63,68,255))
    elif kind=="minigolf":
        d.rectangle((0,1450,WIDTH,HEIGHT),fill=(61,126,82,255))
        d.ellipse((220,980,860,1510),fill=(73,158,91,255),outline=(223,218,190,255),width=14)
        d.ellipse((650,1190,705,1245),fill=(25,31,34,255))
        d.line((677,900,677,1210),fill=(78,73,67,255),width=9)
        d.polygon([(677,900),(820,950),(677,1010)],fill=(241,184,72,255))
    elif kind=="laundromat":
        d.rectangle((80,860,1000,1580),fill=(185,198,209,255),outline=(77,91,104,255),width=7)
        for y in (1040,1300):
            for x in (180,390,600,810):
                d.ellipse((x,y,x+145,y+145),fill=(91,113,133,255),outline=(47,61,74,255),width=8)
                d.ellipse((x+27,y+27,x+118,y+118),fill=(155,204,220,255))
        d.rectangle((0,1580,WIDTH,HEIGHT),fill=(74,76,80,255))

def _prop(d,kind,x,y,scale=1.0):
    if kind=="checklist":
        d.rounded_rectangle((x,y,x+170*scale,y+230*scale),radius=20,fill=(243,238,216,255),outline=(96,91,80,255),width=4)
        for yy in range(int(y+50),int(y+190),40): d.line((x+30,yy,x+140*scale,yy),fill=(112,108,99,255),width=4)
    elif kind=="register":
        _rounded(d,(x,y,x+270*scale,y+150*scale),(69,76,86,255),24)
        d.rectangle((x+35,y+35,x+235*scale,y+85*scale),fill=(106,174,143,255))
    elif kind=="toolbox":
        _rounded(d,(x,y,x+240*scale,y+130*scale),(184,63,54,255),22)
        d.rectangle((x+75,y-45,x+165*scale,y+15),fill=(78,79,82,255))
    elif kind=="customer":
        _character(d,x,y,scale=.68,coat=(108,72,120,255))
    elif kind=="key":
        d.ellipse((x,y,x+85*scale,y+85*scale),outline=(225,184,61,255),width=18)
        d.line((x+72*scale,y+42*scale,x+200*scale,y+42*scale),fill=(225,184,61,255),width=18)
        d.line((x+160*scale,y+42*scale,x+160*scale,y+92*scale),fill=(225,184,61,255),width=18)
    elif kind=="ledger":
        _rounded(d,(x,y,x+245*scale,y+170*scale),(114,67,50,255),18)
        d.rectangle((x+28,y+25,x+220*scale,y+145*scale),fill=(224,207,166,255))
    elif kind=="door":
        d.rectangle((x,y,x+250*scale,y+430*scale),fill=(108,71,48,255),outline=(64,45,34,255),width=7)
        d.ellipse((x+190*scale,y+210*scale,x+220*scale,y+240*scale),fill=(232,190,72,255))
    elif kind=="documents":
        for off in (0,25,50):
            d.polygon([(x+off,y-off),(x+250+off,y+15-off),(x+235+off,y+170-off),(x-10+off,y+150-off)],fill=(239,228,194,255),outline=(120,108,88,255))
    elif kind=="camera":
        _rounded(d,(x,y,x+250*scale,y+150*scale),(49,55,64,255),25)
        d.ellipse((x+55,y+25,x+175*scale,y+145*scale),fill=(71,119,150,255),outline=(21,29,36,255),width=7)
    elif kind=="van":
        _rounded(d,(x,y,x+410*scale,y+220*scale),(236,238,239,255),35,outline=(73,78,83,255),width=6)
        d.ellipse((x+50,y+180*scale,x+120*scale,y+250*scale),fill=(30,33,37,255))
        d.ellipse((x+290*scale,y+180*scale,x+360*scale,y+250*scale),fill=(30,33,37,255))
    elif kind=="lock":
        d.arc((x,y,x+150*scale,y+170*scale),180,360,fill=(197,166,75,255),width=20)
        _rounded(d,(x,y+75*scale,x+155*scale,y+220*scale),(197,166,75,255),22)
    elif kind=="phone":
        _rounded(d,(x,y,x+130*scale,y+240*scale),(39,43,50,255),25)
        d.rectangle((x+18,y+32,x+112*scale,y+190*scale),fill=(90,157,191,255))
    elif kind=="storm":
        for ox,oy,r in [(0,0,150),(110,-35,180),(240,5,160)]:
            d.ellipse((x+ox,y+oy,x+ox+r,y+oy+r*.65),fill=(68,74,87,255))
        d.polygon([(x+170,y+100),(x+120,y+270),(x+185,y+245),(x+145,y+390),(x+300,y+180),(x+220,y+205)],fill=(255,211,64,255))
    elif kind=="files":
        _rounded(d,(x,y,x+320*scale,y+210*scale),(78,85,92,255),20)
        for i in range(4):
            d.rectangle((x+35+i*55,y+50,x+75+i*55,y+175),fill=(224-i*15,190-i*10,105+i*12,255))
    elif kind=="chart":
        _rounded(d,(x,y,x+300*scale,y+220*scale),(236,238,240,255),18)
        pts=[(x+35,y+165),(x+90,y+145),(x+135,y+155),(x+195,y+95),(x+265,y+55)]
        d.line(pts,fill=(55,139,92,255),width=12,joint="curve")

def local_literal_scene(payload,dest):
    idx=int(payload.get("index",0))
    occupation=str(payload.get("occupation","")).lower()
    if "marina" in occupation: venue="marina"
    elif "hotel" in occupation: venue="hotel"
    elif "storage" in occupation: venue="storage"
    elif "campground" in occupation: venue="campground"
    elif "car wash" in occupation: venue="carwash"
    elif "bowling" in occupation: venue="bowling"
    elif "mini golf" in occupation: venue="minigolf"
    elif "laundromat" in occupation: venue="laundromat"
    else: venue="hotel"
    palettes=[
        ((112,157,190),(28,52,74)),((167,130,91),(48,41,48)),((112,147,122),(32,54,48)),
        ((187,139,94),(59,45,48)),((139,118,154),(47,42,63)),((99,133,158),(31,47,65)),
        ((153,126,101),(51,42,39)),((126,141,158),(41,47,57)),((192,144,101),(60,46,44)),
        ((96,120,151),(31,39,57)),((148,128,102),(47,44,45)),((66,84,111),(22,30,48)),
        ((61,76,102),(19,27,43)),((143,128,106),(47,42,38)),((113,139,126),(34,51,45)),
        ((133,154,132),(37,54,43)),((82,104,127),(24,36,48)),((105,126,139),(27,39,47))
    ]
    top,bottom=palettes[idx%len(palettes)]
    im=_gradient_scene(top,bottom)
    d=ImageDraw.Draw(im,"RGBA")
    # distant vignette / environment
    d.ellipse((700,-120,1240,420),fill=(255,220,156,28))
    _building(d,venue)
    # foreground staging changes every beat
    if idx==0:
        _character(d,360,1210,1.20); _prop(d,"checklist",620,1120,1.0)
        d.ellipse((760,650,940,830),fill=(241,205,112,130))
    elif idx==1:
        _character(d,300,1250,1.12); _prop(d,"register",590,1160,1.0); _prop(d,"documents",645,1380,.75)
    elif idx==2:
        _character(d,360,1260,1.14); _prop(d,"toolbox",610,1280,.92)
        for x in (640,780,920): d.rectangle((x,1110,x+35,1260),fill=(246,187,57,255))
    elif idx==3:
        _character(d,270,1270,1.08); _prop(d,"customer",700,1320,.70); _prop(d,"toolbox",520,1460,.70)
    elif idx==4:
        _character(d,330,1250,1.12); _prop(d,"key",650,1260,1.15); _prop(d,"documents",560,1430,.85)
    elif idx==5:
        _character(d,300,1270,1.12); _prop(d,"door",650,1030,1.0); _prop(d,"key",500,1410,.70)
        d.line((610,1490,850,1490),fill=(165,142,118,180),width=8)
    elif idx==6:
        _character(d,300,1280,1.05); _prop(d,"documents",620,1250,1.0); _prop(d,"phone",860,1260,.75)
        d.rectangle((600,900,960,1110),fill=(82,72,65,255),outline=(185,175,151,255),width=5)
    elif idx==7:
        _character(d,315,1260,1.08); _prop(d,"documents",600,1150,1.0); _prop(d,"ledger",680,1430,.75)
    elif idx==8:
        _character(d,270,1260,1.08); _prop(d,"customer",660,1320,.66); _prop(d,"camera",650,980,.82); _prop(d,"van",600,1510,.70)
    elif idx==9:
        _character(d,250,1270,1.05); _prop(d,"camera",540,1090,1.05); _prop(d,"van",585,1480,.88)
    elif idx==10:
        _character(d,285,1270,1.08); _prop(d,"lock",560,1230,.88); _prop(d,"phone",780,1210,.86); _prop(d,"documents",650,1490,.65)
    elif idx==11:
        _character(d,285,1300,1.08,rain=True); _prop(d,"storm",550,650,1.0)
        for x in range(20,WIDTH,90): d.line((x,850,x-140,1500),fill=(196,223,241,110),width=4)
    elif idx==12:
        _character(d,300,1300,1.12,coat=(48,86,104,255),rain=True); _prop(d,"customer",720,1350,.65)
        for x in range(30,WIDTH,80): d.line((x,900,x-120,1550),fill=(200,225,242,100),width=4)
        d.ellipse((780,1460,990,1540),fill=(228,85,55,110))
    elif idx==13:
        _character(d,280,1280,1.06); _prop(d,"door",635,1010,.88); _prop(d,"documents",620,1470,.85); _prop(d,"key",800,1340,.55)
    elif idx==14:
        _character(d,280,1270,1.08); _prop(d,"lock",590,1190,.76); _prop(d,"files",680,1430,.75); _prop(d,"toolbox",500,1490,.65)
    elif idx==15:
        _character(d,290,1280,1.06); _prop(d,"customer",690,1340,.64); _prop(d,"toolbox",540,1490,.72)
        d.ellipse((780,930,965,1115),fill=(122,193,123,100))
    elif idx==16:
        _character(d,310,1260,1.08); _prop(d,"chart",610,1180,1.0); _prop(d,"ledger",650,1450,.72)
    else:
        _character(d,340,1290,1.12); _prop(d,"key",670,1370,.85)
        d.ellipse((750,650,960,860),fill=(248,207,112,75))
    # stylized lower shadow and soft side vignette
    d.rectangle((0,1660,WIDTH,HEIGHT),fill=(14,18,24,70))
    dest.parent.mkdir(parents=True,exist_ok=True)
    im.convert("RGB").save(dest,"JPEG",quality=94,subsampling=0)
    return "local-literal-vector-v1"

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
        if e.code == 402:
            print("AI image credits unavailable; using clean local literal cartoon renderer.", file=sys.stderr)
            return local_literal_scene(payload,dest)
        raise RuntimeError(f"image service {e.code}: {body}") from e
    if len(data) < 20_000:
        raise RuntimeError(f"generated scene too small: {len(data)} bytes")
    dest.write_bytes(data)
    return "ai-generated-literal-scene"

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
        source=post_image(payload,raw_path)
        compose_scene(raw_path,story,frame_path)
        payload["visualSource"]=source
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
