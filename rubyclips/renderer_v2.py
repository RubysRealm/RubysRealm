#!/usr/bin/env python3
import asyncio
import json
import math
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import pipeline as p

W, H = p.WIDTH, p.HEIGHT


def safe_ass_escape(text):
    # Keep ASS line-break tokens (\N) intact; only protect override delimiters.
    return str(text).replace("{", r"\{").replace("}", r"\}")


def fast_request_image(scene, previous_scene, next_scene, index, season, episode, path):
    if not p.OIDC_TOKEN:
        raise RuntimeError("Missing GitHub OIDC token")
    payload = {
        "mode": "rubyclips-drama",
        "title": p.SERIES_TITLE,
        "part": f"Season {season}, Episode {episode}",
        "beat": scene,
        "previousBeat": previous_scene or "",
        "nextBeat": next_scene or "",
        "index": index,
        "seed": p.RUN_SEED + index + season * 100 + episode * 10,
        "cast": p.CAST_BIBLE,
    }
    body = json.dumps(payload).encode()
    last = None
    for attempt in range(3):
        req = urllib.request.Request(
            p.IMAGE_URL,
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {p.OIDC_TOKEN}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            if len(data) < 10000:
                raise RuntimeError(f"image response too small: {len(data)}")
            path.write_bytes(data)
            return True
        except urllib.error.HTTPError as exc:
            # No paid top-up: if the existing image-credit reserve is unavailable,
            # immediately use our original local visual renderer instead of wasting retries.
            if exc.code == 402:
                raise RuntimeError("AI image credit reserve unavailable; using local original renderer")
            last = exc
        except Exception as exc:
            last = exc
        time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"image generation failed after retries: {last}")


def lerp(a, b, q):
    return int(a * (1 - q) + b * q)


def gradient(top, bottom):
    im = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(im)
    for y in range(H):
        q = y / (H - 1)
        d.line((0, y, W, y), fill=tuple(lerp(top[i], bottom[i], q) for i in range(3)))
    return im


def glow(im, xy, radius=220, strength=65):
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    x, y = xy
    for r in range(radius, 10, -14):
        a = max(0, int(strength * (1 - r / radius) * 0.35))
        ld.ellipse((x-r, y-r, x+r, y+r), fill=(255, 205, 130, a))
    return Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")


def person(d, x, y, who, scale=1.0, pose="neutral"):
    profiles = {
        "Maya": {"skin": (220, 171, 142), "hair": (94, 45, 37), "coat": (29, 55, 92), "pants": (27, 31, 40)},
        "Adrian": {"skin": (211, 164, 137), "hair": (29, 29, 34), "coat": (48, 49, 58), "pants": (25, 27, 34)},
        "Elise": {"skin": (226, 184, 155), "hair": (207, 183, 139), "coat": (210, 199, 180), "pants": (58, 59, 64)},
        "Graham": {"skin": (213, 176, 151), "hair": (171, 176, 181), "coat": (31, 54, 80), "pants": (31, 34, 41)},
    }
    c = profiles.get(who, profiles["Adrian"])
    s = scale
    def box(a,b,cx,dy): return (int(x+a*s), int(y+b*s), int(x+cx*s), int(y+dy*s))
    # shadow
    d.ellipse(box(-78, 282, 78, 330), fill=(0, 0, 0, 65))
    # legs
    d.rounded_rectangle(box(-52, 130, -8, 292), radius=max(8,int(16*s)), fill=c["pants"])
    d.rounded_rectangle(box(8, 130, 52, 292), radius=max(8,int(16*s)), fill=c["pants"])
    d.ellipse(box(-65, 272, 4, 316), fill=(18, 20, 26))
    d.ellipse(box(-4, 272, 65, 316), fill=(18, 20, 26))
    # torso
    d.rounded_rectangle(box(-88, -2, 88, 165), radius=max(18,int(42*s)), fill=c["coat"], outline=(18,18,24), width=max(2,int(3*s)))
    # shirt/lapel
    d.polygon([(int(x-36*s),int(y+4*s)),(int(x),int(y+66*s)),(int(x+36*s),int(y+4*s))], fill=(224, 225, 227))
    # arms, with simple expressive poses
    if pose == "point":
        d.rounded_rectangle(box(-125, 20, -78, 155), radius=max(10,int(20*s)), fill=c["coat"])
        d.line((int(x+78*s),int(y+38*s),int(x+170*s),int(y+5*s)), fill=c["coat"], width=max(18,int(34*s)))
        d.ellipse(box(155, -12, 184, 17), fill=c["skin"])
    elif pose == "phone":
        d.rounded_rectangle(box(-120, 20, -77, 155), radius=max(10,int(20*s)), fill=c["coat"])
        d.line((int(x+78*s),int(y+38*s),int(x+118*s),int(y-55*s)), fill=c["coat"], width=max(18,int(34*s)))
        d.rounded_rectangle(box(108, -85, 137, -20), radius=5, fill=(15,18,23), outline=(155,165,180), width=2)
    else:
        d.rounded_rectangle(box(-123, 20, -78, 158), radius=max(10,int(20*s)), fill=c["coat"])
        d.rounded_rectangle(box(78, 20, 123, 158), radius=max(10,int(20*s)), fill=c["coat"])
    # neck/head
    d.rounded_rectangle(box(-23, -38, 23, 10), radius=12, fill=c["skin"])
    d.ellipse(box(-66, -154, 66, -24), fill=c["skin"], outline=(52,43,41), width=max(2,int(3*s)))
    # hair styles
    if who == "Maya":
        d.pieslice(box(-68,-160,68,-35), 180, 360, fill=c["hair"])
        d.rounded_rectangle(box(-70,-118,-46,-12), radius=9, fill=c["hair"])
        d.rounded_rectangle(box(46,-118,70,-12), radius=9, fill=c["hair"])
    elif who == "Elise":
        d.pieslice(box(-68,-160,68,-38), 180, 360, fill=c["hair"])
        d.rounded_rectangle(box(40,-110,70,-30), radius=8, fill=c["hair"])
    else:
        d.pieslice(box(-63,-157,63,-50), 180, 360, fill=c["hair"])
    # face
    d.ellipse(box(-31,-94,-18,-81), fill=(26,29,35))
    d.ellipse(box(18,-94,31,-81), fill=(26,29,35))
    d.arc(box(-25,-70,25,-38), 15, 165, fill=(99,57,51), width=max(2,int(3*s)))


def window_wall(d, y0=420, y1=1450, night=True):
    d.rectangle((45, y0, W-45, y1), fill=(26, 37, 56), outline=(91, 107, 132), width=5)
    for x in range(85, W-70, 180):
        d.line((x, y0, x, y1), fill=(66, 82, 105), width=4)
    for y in range(y0+120, y1, 180):
        d.line((45, y, W-45, y), fill=(60, 75, 99), width=3)
    if night:
        for x in range(100, W-90, 110):
            for y in range(y0+70, y1-40, 105):
                if (x//110 + y//105) % 3 == 0:
                    d.rectangle((x,y,x+28,y+42), fill=(225, 177, 92))


def desk(d, y=1260, paper=False, phone=False, coffee=False, watch=False):
    d.rounded_rectangle((90,y,W-90,y+260), radius=24, fill=(72,48,39), outline=(132,96,74), width=5)
    d.rectangle((125,y+260,180,H), fill=(45,34,31))
    d.rectangle((W-180,y+260,W-125,H), fill=(45,34,31))
    if paper:
        d.polygon([(325,y+35),(760,y+55),(720,y+210),(295,y+190)], fill=(237,231,213), outline=(150,141,127))
        for k in range(5): d.line((360,y+78+k*24,680,y+88+k*24), fill=(119,112,103), width=4)
        d.ellipse((640,y+160,690,y+210), fill=(142,45,38))
    if phone:
        d.rounded_rectangle((760,y+55,840,y+185), radius=14, fill=(13,17,23), outline=(146,161,181), width=4)
        d.rectangle((772,y+72,828,y+158), fill=(38,92,127))
    if coffee:
        d.ellipse((210,y+50,305,y+90), fill=(225,225,218), outline=(120,120,120), width=3)
        d.rectangle((210,y+70,305,y+145), fill=(231,229,219), outline=(120,120,120), width=3)
        d.ellipse((228,y+72,287,y+88), fill=(83,52,37))
    if watch:
        d.ellipse((465,y+70,545,y+150), fill=(28,31,37), outline=(192,188,170), width=5)
        d.line((505,y+73,505,y+25), fill=(55,55,58), width=12)
        d.line((505,y+147,505,y+195), fill=(55,55,58), width=12)


def corridor(d, sealed=False):
    d.polygon([(80,520),(W-80,520),(760,1540),(320,1540)], fill=(72,76,84))
    d.polygon([(80,520),(320,1540),(0,H),(0,420)], fill=(54,58,66))
    d.polygon([(W-80,520),(W,420),(W,H),(760,1540)], fill=(49,53,61))
    d.polygon([(80,520),(W-80,520),(760,260),(320,260)], fill=(39,44,53))
    for y in (660,870,1080,1290):
        q=(y-520)/(1020)
        xl=int(80+(320-80)*q); xr=int(W-80+(760-(W-80))*q)
        d.line((xl,y,xr,y), fill=(110,113,117), width=3)
    for side in (-1,1):
        xs = [160, 255, 335] if side<0 else [W-160,W-255,W-335]
        for i,x in enumerate(xs):
            yy=650+i*260
            w=90+i*18
            d.rectangle((x-w//2,yy,x+w//2,yy+175+i*18), fill=(41,45,53), outline=(124,112,92), width=4)
    if sealed:
        for x in (180, 520, 850):
            d.polygon([(x,1480),(x+70,1480),(x+130,1600),(x-45,1600)], fill=(105,101,94))


def monitor_wall(d):
    d.rectangle((115,500,965,1340), fill=(23,27,34), outline=(111,122,141), width=8)
    screens=[(160,560,505,900),(575,560,920,900),(160,970,505,1280),(575,970,920,1280)]
    for i,b in enumerate(screens):
        d.rectangle(b, fill=(47,65,76), outline=(96,113,125), width=4)
        x0,y0,x1,y1=b
        d.rectangle((x0+25,y1-95,x1-25,y1-40), fill=(31,34,39))
        d.line((x0+45,y1-100,x1-55,y0+85), fill=(123,130,133), width=5)
        if i==0:
            d.rounded_rectangle((x0+140,y0+105,x0+235,y0+245), radius=20, fill=(215,202,180))
            d.ellipse((x0+165,y0+68,x0+215,y0+118), fill=(220,180,150))


def boardroom(d):
    window_wall(d, 360, 1080, night=False)
    d.polygon([(135,1050),(945,1050),(1030,1600),(50,1600)], fill=(66,47,38), outline=(129,94,72))
    for x in range(170,900,145):
        d.ellipse((x,1075,x+70,1130), fill=(37,40,47))
    d.rectangle((0,1600,W,H), fill=(47,49,53))


def rooftop(d):
    # warm sunrise skyline
    for x,h,w in [(20,430,170),(205,610,120),(345,500,180),(550,720,155),(720,560,130),(870,650,190)]:
        d.rectangle((x,H-h,x+w,H), fill=(46,52,67))
        for yy in range(H-h+40,H-50,85):
            for xx in range(x+25,min(W,x+w-20),50):
                d.rectangle((xx,yy,xx+18,yy+30), fill=(215,181,121))
    d.rectangle((0,1450,W,H), fill=(48,51,58))
    d.line((0,1450,W,1450), fill=(130,132,137), width=6)


def scene_specific_background(visual, index):
    v = visual.lower()
    if "rooftop" in v or "sunrise" in v:
        im=gradient((224,142,92),(39,58,92)); d=ImageDraw.Draw(im); rooftop(d); return im,d
    if "corridor" in v or "floor" in v or "service elevator" in v:
        im=gradient((31,37,48),(10,13,19)); d=ImageDraw.Draw(im); corridor(d, sealed=True); return im,d
    if "security monitor" in v or "surveillance" in v or "camera" in v:
        im=gradient((18,25,36),(7,10,15)); d=ImageDraw.Draw(im); monitor_wall(d); return im,d
    if "boardroom" in v or "board" in v and "meeting" in v:
        im=gradient((116,137,165),(25,31,44)); d=ImageDraw.Draw(im); boardroom(d); return im,d
    if "penthouse" in v:
        im=gradient((26,38,61),(11,15,24)); d=ImageDraw.Draw(im); window_wall(d,360,1260,night=True); desk(d,1230,paper=False,phone=True,coffee=True,watch=True); return im,d
    if "bar" in v or "lobby" in v:
        im=gradient((67,45,43),(19,22,31)); d=ImageDraw.Draw(im); window_wall(d,440,1180,night=True); desk(d,1270,paper=True,coffee=True); return im,d
    if "abandoned law office" in v or "shredder" in v:
        im=gradient((79,77,70),(22,24,28)); d=ImageDraw.Draw(im); window_wall(d,440,1050,night=False); desk(d,1240,paper=True); d.rectangle((820,1050,965,1350),fill=(42,44,49),outline=(128,128,122),width=4); return im,d
    if "garage" in v:
        im=gradient((46,54,62),(16,18,23)); d=ImageDraw.Draw(im); d.rectangle((0,1320,W,H),fill=(48,50,53));
        for x in (120,540): d.rounded_rectangle((x,980,x+420,1280),radius=65,fill=(178,183,190),outline=(47,49,55),width=6)
        return im,d
    # default premium office / legal setting
    im=gradient((31,43,66),(12,16,25)); d=ImageDraw.Draw(im); window_wall(d,350,1140,night=True); desk(d,1260,paper=True,phone="phone" in v,coffee="coffee" in v,watch="watch" in v); return im,d


def fallback_image_v2(index, path):
    state=json.loads(p.STATE_PATH.read_text())
    episode=min(p.TOTAL_EPISODES,max(1,int(state.get("episodeNumber",1))))
    visual=p.EPISODES[episode]["scenes"][index][0]
    v=visual.lower()
    im,d=scene_specific_background(visual,index)

    # scene-specific foreground props
    if "contract" in v or "document" in v or "signature" in v or "transfer clause" in v:
        d.polygon([(285,1160),(800,1180),(750,1450),(245,1415)],fill=(242,235,218),outline=(133,122,109),width=4)
        for yy in range(1220,1380,35): d.line((330,yy,690,yy+8),fill=(128,119,108),width=4)
        d.ellipse((650,1340,715,1405),fill=(143,47,42))
    if "sealed contract" in v or "sealed envelope" in v:
        d.polygon([(310,1160),(760,1160),(760,1400),(310,1400)],fill=(226,214,188),outline=(121,105,85),width=4)
        d.polygon([(310,1160),(535,1320),(760,1160)],fill=(205,190,160),outline=(121,105,85))
    if "cabinet" in v:
        d.rectangle((780,650,1010,1340),fill=(79,84,91),outline=(163,169,178),width=6)
        d.ellipse((900,970,930,1000),fill=(226,190,95))
    if "photograph" in v or "photographs" in v:
        d.rectangle((180,1150,430,1420),fill=(232,226,208),outline=(111,102,89),width=5)
        d.rectangle((205,1180,405,1360),fill=(115,109,99))
        d.ellipse((270,1210,340,1280),fill=(207,165,134))
    if "recorder" in v or "audio file" in v:
        d.rounded_rectangle((455,1190,670,1330),radius=22,fill=(28,31,36),outline=(164,169,176),width=4)
        d.circle((505,1260),24,fill=(186,50,44)); d.rectangle((555,1235,635,1285),fill=(50,85,103))
    if "network" in v or "server" in v:
        for x in (110,375,640):
            d.rectangle((x,670,x+225,1370),fill=(29,33,39),outline=(104,114,127),width=5)
            for yy in range(720,1320,80):
                d.rectangle((x+25,yy,x+200,yy+45),fill=(50,57,67)); d.ellipse((x+170,yy+12,x+186,yy+28),fill=(93,196,122))
    if "hidden door" in v:
        d.rectangle((760,560,1030,1450),fill=(37,42,49),outline=(121,128,137),width=6)
        d.line((790,600,1000,1420),fill=(75,80,89),width=5)

    # recurring cast placement chosen from text
    people=[]
    if "maya" in v or True: people.append(("Maya",325))
    if "adrian" in v or any(k in v for k in ["confront", "penthouse", "corridor", "boardroom", "rooftop", "hotel"]): people.append(("Adrian",730))
    if "elise" in v or "cream coat" in v: people.append(("Elise",890 if len(people)>1 else 720))
    if "graham" in v and "phone" not in v: people.append(("Graham",530))
    # de-duplicate and cap to keep composition readable
    seen=set(); clean=[]
    for who,x in people:
        if who not in seen:
            seen.add(who); clean.append((who,x))
    clean=clean[:3]
    if len(clean)==1: clean=[(clean[0][0],540)]
    elif len(clean)==3: clean=[(clean[0][0],250),(clean[1][0],540),(clean[2][0],830)]
    for j,(who,x) in enumerate(clean):
        pose="point" if ("confront" in v or "points" in v or "shows" in v) and j==0 else ("phone" if "phone" in v and j==0 else "neutral")
        person(d,x,790 if "desk" not in v else 800,who,1.05,pose)

    # subtle vignette to give the vector frames more cinematic depth
    overlay=Image.new("RGBA",(W,H),(0,0,0,0)); od=ImageDraw.Draw(overlay)
    for n in range(14):
        inset=n*20; alpha=max(0,6+n*3)
        od.rounded_rectangle((inset,inset,W-inset,H-inset),radius=80,outline=(0,0,0,alpha),width=34)
    im=Image.alpha_composite(im.convert("RGBA"),overlay).convert("RGB")
    im.save(path,quality=94,subsampling=0)


async def run_v2():
    p.ass_escape = safe_ass_escape
    p.request_image = fast_request_image
    p.fallback_image = fallback_image_v2
    await p.main()
    manifest_path = p.OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["rendererVersion"] = "rubyclips-vector-drama-v2"
    manifest["captionRenderer"] = "ass-v2-linebreak-safe"
    manifest["localFallbackRenderer"] = "scene-aware-original-vector-v2"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    asyncio.run(run_v2())
