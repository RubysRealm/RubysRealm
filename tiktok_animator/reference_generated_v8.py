import json, os, random, urllib.request, urllib.error
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFilter

SERVICE_FAILURES=0

PREGENERATED_PREMIUM_SCENES=["https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/deff9573-ee7e-4dab-916f-eb38d303c75c/Single_standalone_vertical_story_illustration__unmistakably_.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiYjI5MGJmMjQyODY5N2FiZCIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODIxNzc2NH0.mTuRaaNtOqy9sEx-KPp_tRURQsbzW8QliwLWmhgPqc8","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/0e711935-4e44-49ae-8a41-658dd94810fd/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiOTM0ZmRiNzMzNGU4OTMyZSIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODIzMzA3NX0.fXqt4EdMVjfDKUAKr1L31HebYNuu96SLpQz25Ht_NZo","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/dd3b91ca-05ae-41b5-873d-cadfbf21fabd/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiOThlNjJhYjU5NjQ4MDkwMCIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODIyNTg0NX0.UEmKYl20iEdb9-75dOLVoJntM3S4YpErmu14LP6REEs","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/a2828c3a-71aa-4ccd-999c-0df8367f5107/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiNWE4ZTk1MTdlZTIxMDcyYyIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODE3MDUxOX0.Avim8T9ay0l38V_sbCj9-uhngf7b9GYhBO7FjWi3iW0","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/20190187-ac76-4496-88a5-71695ef16de5/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiNDY5ZTFlYmRjZjI5YTZkNyIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODE4NTI3N30.6DKqnYcL9j6fKRMfc4wsUZ_tuJ9q2zffc5iHyuabHAY","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/324a0327-cfdd-47ff-8a42-32ca6a28421a/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiOGEzMDUwMzZlZTNiODkyMyIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODE4NTI3MH0.vsv-oBX8VwJuFrXblDVP-YAv7cU7lWW6L1fA3NWkICA","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/71339cbf-18fc-40f8-a5e9-2b94562ed426/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiMGQwOGNlMGYzY2ZhMjVlMyIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODIyMzI0N30.nYPeZc9U8VtfvczWbtB_AMaWuss9_i6yBqRB3-syBqg","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/3c62ecd1-c39f-4fdc-b2ec-647ef0dad9c1/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiYTZmNTY3MWNmMDliZjM1NyIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODIzMzM3Mn0.bbbqE9Ec8QpQFLeRZjUqY46ZY6r2o4xbiF2FhBs9DHQ","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/35af4131-4f28-4b09-9949-b2f10c52c1bb/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiZDNjZjFjNWM3OTg5Nzc2NCIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODE1NDU4OH0.eAn3g2KA1M4JMi2SLYku4LqeJtJPmzLnJcLJBrFU0mg","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/6a1a2683-b373-469d-81a7-c5eade4007d5/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiNjFiMmJhYThkMWRiODZjNyIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODIyOTU0NH0.II1r-9FAROFO5X2JlY6ezvvOY1uvGf05Knn91SQogrw","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/b7675b47-5406-47e1-a982-0ab90c784cfb/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiYjdjYmQwNWU0YjNjZWU4MyIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODE5MjQ3OH0.1fZ4ueHQM1tSKyt1b00EuMXvIpWHyrTU1jB37o2duxU","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/c04dfdd9-7a59-46ce-a759-989daa161ef2/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiY2E4ZmRkOTYwNDk5MTlkNSIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODE4OTIwNn0.wR5YllrfQdrzgd0E7rgxdrhhOe8lorv8Qo3ybDo7Rao","https://dnznrvs05pmza.cloudfront.net/gemini/gemini-3.1-flash-lite-image/images/94b1efa6-699a-4e0a-ad37-ee43ed77fe95/Preserve__hero_s_exact_adult_character_design_and_the_same_p.jpg?_jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJrZXlIYXNoIjoiOWQ5ZGFiMDFmZGM4OGM3MSIsImJ1Y2tldCI6InJ1bndheS10YXNrLWFydGlmYWN0cyIsInN0YWdlIjoicHJvZCIsImV4cCI6MTc4ODIxODI0MX0.cTYRSIXOX7uki3TdCg91uXf2Kr9LEiJGIFlH3CPuh9Q"]




def _is_generated(source):
    return (source or {}).get('source_type') in ('ai-generated-illustration','procedural-generated-illustration')


def _scene_kind(text):
    import re
    t=re.sub(r'[^a-z0-9]+',' ',str(text or '').lower()).strip()
    groups=[
        ('storage',('storage','auction','locker','warehouse','unit','box','crate','bay')),
        ('motel',('motel','hotel','room','lobby','keycard','front desk')),
        ('document',('note','letter','paper','receipt','document','map','photo','photograph','survey','plan','filing','contract','record')),
        ('phone',('phone','call','message','texted','screen','voicemail','monitor','camera','cctv')),
        ('door',('door','lock','key','hallway','entrance','gate')),
        ('money',('cash','money','wallet','payment','bank','safe','coin')),
        ('vehicle',('car','truck','van','road','drive','parking','garage','vehicle')),
        ('mountain',('mountain','lodge','cabin','snow','ridge','trail','forest')),
        ('storm',('storm','rain','lightning','wind','dark cloud')),
        ('fire',('fire','smoke','burn','flame','alarm')),
        ('police',('police','officer','siren','crime','investigator','deputy','law enforcement')),
    ]
    padded=' '+t+' '
    for kind,words in groups:
        for w in words:
            phrase=' '+re.sub(r'[^a-z0-9]+',' ',w.lower()).strip()+' '
            if phrase in padded:
                return kind
    return 'mystery'


def _gradient(size,top,bottom):
    w,h=size
    im=Image.new('RGB',size,top)
    d=ImageDraw.Draw(im)
    for y in range(h):
        q=y/max(1,h-1)
        col=tuple(int(top[i]*(1-q)+bottom[i]*q) for i in range(3))
        d.line((0,y,w,y),fill=col)
    return im


def _protagonist(layer,x,y,scale=1.0,facing=1):
    d=ImageDraw.Draw(layer,'RGBA')
    s=scale
    def box(a,b,c,dv): return (int(x+a*s),int(y+b*s),int(x+c*s),int(y+dv*s))
    # soft cast shadow
    shadow=Image.new('RGBA',layer.size,(0,0,0,0)); sd=ImageDraw.Draw(shadow,'RGBA')
    sd.ellipse(box(-95,315,105,365),fill=(0,0,0,95))
    shadow=shadow.filter(ImageFilter.GaussianBlur(int(16*s)))
    layer.alpha_composite(shadow)
    # legs and shoes
    d.rounded_rectangle(box(-58,175,-10,326),radius=int(20*s),fill=(38,42,50,255))
    d.rounded_rectangle(box(16,175,64,326),radius=int(20*s),fill=(32,36,44,255))
    d.ellipse(box(-76,302,0,342),fill=(20,22,27,255))
    d.ellipse(box(2,302,82,342),fill=(20,22,27,255))
    # hoodie torso with highlight
    d.rounded_rectangle(box(-92,34,94,214),radius=int(58*s),fill=(48,54,64,255))
    d.rounded_rectangle(box(-70,48,55,184),radius=int(42*s),fill=(66,73,84,255))
    d.arc(box(-66,54,66,180),180,350,fill=(105,113,126,180),width=max(2,int(5*s)))
    # arms
    d.rounded_rectangle(box(-128,58,-70,196),radius=int(26*s),fill=(52,58,68,255))
    d.rounded_rectangle(box(70,58,128,196),radius=int(26*s),fill=(52,58,68,255))
    # neck/head
    d.rounded_rectangle(box(-28,-10,30,46),radius=int(16*s),fill=(185,132,104,255))
    d.ellipse(box(-66,-98,66,34),fill=(202,151,120,255))
    d.ellipse(box(-54,-88,58,20),fill=(218,167,135,255))
    # ears
    d.ellipse(box(-78,-55,-54,-20),fill=(192,138,111,255))
    d.ellipse(box(54,-55,78,-20),fill=(192,138,111,255))
    # simple expressive face
    eye_y=-42
    if facing>=0:
        d.ellipse(box(-22,eye_y,-10,eye_y+12),fill=(28,31,36,255))
        d.ellipse(box(18,eye_y,30,eye_y+12),fill=(28,31,36,255))
    else:
        d.ellipse(box(-30,eye_y,-18,eye_y+12),fill=(28,31,36,255))
        d.ellipse(box(10,eye_y,22,eye_y+12),fill=(28,31,36,255))
    d.arc(box(-26,-18,28,16),10,170,fill=(72,45,38,220),width=max(2,int(4*s)))
    # head rim light
    d.arc(box(-60,-92,60,28),205,330,fill=(255,220,190,130),width=max(2,int(5*s)))


def _main_object(layer,kind,x,y,s=1.0):
    d=ImageDraw.Draw(layer,'RGBA')
    def B(a,b,c,dv): return (int(x+a*s),int(y+b*s),int(x+c*s),int(y+dv*s))
    # shared shadow
    sh=Image.new('RGBA',layer.size,(0,0,0,0)); sd=ImageDraw.Draw(sh,'RGBA')
    sd.ellipse(B(-150,170,150,225),fill=(0,0,0,90)); sh=sh.filter(ImageFilter.GaussianBlur(max(8,int(18*s))))
    layer.alpha_composite(sh)
    if kind=='mountain':
        d.polygon([(x-190*s,y+150*s),(x-40*s,y-95*s),(x+40*s,y+15*s),(x+135*s,y-135*s),(x+225*s,y+150*s)],fill=(74,91,112,255))
        d.polygon([(x-40*s,y-95*s),(x-92*s,y-8*s),(x-12*s,y-18*s)],fill=(224,235,244,255))
        d.polygon([(x+135*s,y-135*s),(x+88*s,y-62*s),(x+162*s,y-76*s)],fill=(235,242,247,255))
        d.rounded_rectangle(B(-95,70,85,190),radius=int(16*s),fill=(116,72,46,255))
        d.polygon([(x-120*s,y+82*s),(x-5*s,y+8*s),(x+110*s,y+82*s)],fill=(72,42,31,255))
        d.rectangle(B(-28,118,18,190),fill=(38,29,26,255))
    elif kind=='storage':
        d.rounded_rectangle(B(-155,-95,155,185),radius=int(22*s),fill=(114,130,148,255),outline=(51,61,72,255),width=max(3,int(8*s)))
        for yy in range(-65,150,45):
            d.line((x-135*s,y+yy*s,x+135*s,y+yy*s),fill=(74,86,99,210),width=max(2,int(5*s)))
        d.rounded_rectangle(B(-62,20,60,170),radius=int(18*s),fill=(168,111,55,255))
        d.polygon([(x-62*s,y+20*s),(x+5*s,y-20*s),(x+60*s,y+20*s)],fill=(199,142,77,255))
    elif kind=='motel':
        d.rounded_rectangle(B(-180,-115,180,185),radius=int(18*s),fill=(210,171,105,255))
        for xx in (-125,-40,45):
            d.rounded_rectangle(B(xx,-62,xx+62,-4),radius=int(8*s),fill=(70,134,170,255))
            d.rounded_rectangle(B(xx,58,xx+62,170),radius=int(8*s),fill=(88,64,49,255))
        d.rectangle(B(-190,20,190,42),fill=(135,87,55,255))
    elif kind=='vehicle':
        d.rounded_rectangle(B(-175,15,175,145),radius=int(48*s),fill=(83,116,151,255))
        d.polygon([(x-110*s,y+15*s),(x-45*s,y-70*s),(x+75*s,y-70*s),(x+130*s,y+15*s)],fill=(66,94,122,255))
        d.polygon([(x-82*s,y+5*s),(x-34*s,y-52*s),(x+56*s,y-52*s),(x+94*s,y+5*s)],fill=(151,205,225,230))
        d.ellipse(B(-125,108,-55,178),fill=(27,31,36,255)); d.ellipse(B(55,108,125,178),fill=(27,31,36,255))
        d.ellipse(B(-105,126,-75,156),fill=(118,125,133,255)); d.ellipse(B(75,126,105,156),fill=(118,125,133,255))
    elif kind=='money':
        d.rounded_rectangle(B(-155,-45,155,160),radius=int(28*s),fill=(69,92,72,255))
        for k in range(4):
            off=k*16*s
            d.rounded_rectangle((x-130*s+off,y-20*s-off,x+90*s+off,y+70*s-off),radius=int(12*s),fill=(104,172,104,255),outline=(47,104,55,255),width=max(2,int(5*s)))
            d.ellipse((x-30*s+off,y+2*s-off,x+26*s+off,y+58*s-off),fill=(172,218,143,255))
        d.ellipse(B(35,65,150,180),fill=(214,170,59,255)); d.ellipse(B(56,86,128,158),fill=(242,205,83,255))
    elif kind=='phone':
        d.rounded_rectangle(B(-95,-135,95,190),radius=int(34*s),fill=(35,39,46,255))
        d.rounded_rectangle(B(-76,-102,76,145),radius=int(18*s),fill=(84,157,193,255))
        d.ellipse(B(-18,158,18,194),fill=(111,118,126,255))
        d.ellipse(B(-35,-35,35,35),fill=(228,240,247,110))
    elif kind=='door':
        d.rounded_rectangle(B(-125,-145,125,190),radius=int(12*s),fill=(116,73,45,255))
        d.rounded_rectangle(B(-92,-112,92,170),radius=int(8*s),fill=(141,89,53,255))
        d.ellipse(B(48,10,72,34),fill=(228,192,89,255))
        d.rounded_rectangle(B(98,-55,180,45),radius=int(18*s),fill=(61,69,78,255))
        d.ellipse(B(120,-34,156,2),fill=(241,195,79,255))
    elif kind=='document':
        d.polygon([(x-135*s,y-110*s),(x+100*s,y-80*s),(x+130*s,y+165*s),(x-105*s,y+140*s)],fill=(240,230,198,255))
        for yy in (-40,5,50,95):
            d.line((x-75*s,y+yy*s,x+72*s,y+(yy+10)*s),fill=(104,102,95,190),width=max(2,int(5*s)))
        d.ellipse(B(50,85,160,195),outline=(93,65,42,255),width=max(4,int(12*s)))
    elif kind=='storm':
        for ox,oy,r in [(-90,-45,80),(-20,-85,95),(65,-45,85),(5,-5,110)]:
            d.ellipse(B(ox-r/2,oy-r/2,ox+r/2,oy+r/2),fill=(72,78,93,255))
        d.polygon([(x+10*s,y+5*s),(x-30*s,y+92*s),(x+10*s,y+82*s),(x-10*s,y+165*s),(x+72*s,y+55*s),(x+28*s,y+66*s)],fill=(255,223,82,255))
    elif kind=='fire':
        d.polygon([(x,y-130*s),(x-95*s,y+115*s),(x-25*s,y+80*s),(x,y+175*s),(x+105*s,y+85*s),(x+55*s,y+95*s)],fill=(236,86,38,255))
        d.polygon([(x+5*s,y-55*s),(x-38*s,y+95*s),(x+10*s,y+70*s),(x+24*s,y+130*s),(x+62*s,y+45*s)],fill=(255,190,61,255))
    elif kind=='police':
        d.rounded_rectangle(B(-160,15,160,150),radius=int(45*s),fill=(48,70,101,255))
        d.rounded_rectangle(B(-70,-62,70,20),radius=int(18*s),fill=(67,86,117,255))
        d.rectangle(B(-66,-78,-6,-50),fill=(224,61,61,255)); d.rectangle(B(6,-78,66,-50),fill=(62,128,226,255))
        d.ellipse(B(-125,112,-55,182),fill=(24,28,34,255)); d.ellipse(B(55,112,125,182),fill=(24,28,34,255))
    else:
        d.rounded_rectangle(B(-145,-100,145,175),radius=int(46*s),fill=(79,62,104,255))
        d.ellipse(B(-80,-42,80,118),fill=(130,100,171,255))
        d.ellipse(B(-26,14,26,66),fill=(236,207,92,255))
        d.line((x,y+66*s,x,y+118*s),fill=(245,218,112,255),width=max(3,int(10*s)))


def _procedural_cartoon(beat,seed,dest):
    rng=random.Random(int(seed))
    kind=_scene_kind(beat)
    palettes={
        'mountain':((74,112,156),(24,45,70)),
        'storage':((117,139,162),(50,62,75)),
        'motel':((220,158,93),(87,52,45)),
        'vehicle':((79,116,153),(28,39,58)),
        'money':((89,132,100),(31,57,44)),
        'phone':((81,116,160),(34,43,68)),
        'door':((142,104,77),(49,35,34)),
        'document':((177,151,113),(65,55,48)),
        'storm':((75,82,111),(25,28,46)),
        'fire':((131,71,57),(48,31,39)),
        'police':((73,91,129),(25,34,57)),
        'mystery':((99,78,130),(34,28,53)),
    }
    top,bottom=palettes[kind]
    bg=_gradient((1024,1280),top,bottom).convert('RGBA')
    d=ImageDraw.Draw(bg,'RGBA')
    # cinematic floor / stage with perspective
    d.polygon([(0,760),(1024,690),(1024,1280),(0,1280)],fill=(26,30,36,225))
    for i in range(7):
        y=760+i*82
        d.line((0,y,1024,y-40),fill=(255,255,255,16),width=2)
    # soft rim lights
    glow=Image.new('RGBA',bg.size,(0,0,0,0)); gd=ImageDraw.Draw(glow,'RGBA')
    gd.ellipse((620,-120,1180,520),fill=(255,224,164,36))
    gd.ellipse((-260,320,360,980),fill=(95,183,255,26))
    glow=glow.filter(ImageFilter.GaussianBlur(70)); bg.alpha_composite(glow)
    art=Image.new('RGBA',bg.size,(0,0,0,0))
    _protagonist(art,285,690,1.28,1)
    _main_object(art,kind,735,750,1.22)
    # add foreground depth cues
    ad=ImageDraw.Draw(art,'RGBA')
    for _ in range(8):
        x=rng.randint(20,1004); y=rng.randint(950,1260); rr=rng.randint(6,22)
        ad.ellipse((x-rr,y-rr,x+rr,y+rr),fill=(255,255,255,rng.randint(8,24)))
    bg.alpha_composite(art)
    out=bg.convert('RGB').filter(ImageFilter.GaussianBlur(0.15))
    Path(dest).parent.mkdir(parents=True,exist_ok=True)
    out.save(dest,'JPEG',quality=93)
    return {
        'query':str(beat)[:500],
        'source_type':'procedural-generated-illustration',
        'model':'local-procedural-3d-cartoon-v1',
        'via':'local-no-cost-renderer',
        'seed':int(seed),
        'visualStyle':'hotel-owner-reference-simple-cartoon',
        'sceneKind':kind
    }


def bind(target):
    global SERVICE_FAILURES
    original_ai=target._ai_image
    original_verify=target.verify
    original_select=target.select_visuals

    def ai_image(beat,seed,dest):
        global SERVICE_FAILURES
        # Production default is the local deterministic cartoon renderer: zero API spend,
        # no recycled media, and one fresh beat-matched illustration per scene.
        # Remote image generation is opt-in only and remains behind the existing credit reserve.
        if str(os.getenv('ALLOW_REMOTE_IMAGE_GENERATION','0')).strip().lower() not in ('1','true','yes'):
            return _procedural_cartoon(beat,seed,dest)
        direct=original_ai(beat,seed,dest)
        if direct:
            return direct
        service=str(os.getenv('V7_IMAGE_SERVICE_URL','')).strip()
        token=str(os.getenv('GITHUB_OIDC_TOKEN','')).strip()
        if not service or not token:
            return _procedural_cartoon(beat,seed,dest)
        body=json.dumps({'title':target.CURRENT_TITLE,'beat':str(beat)[:1400],'index':int(seed)%25}).encode()
        last_error=None
        for _attempt in range(2):
            req=urllib.request.Request(service,data=body,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','User-Agent':'RubysRealmGitHubRenderer/8.1'})
            try:
                with urllib.request.urlopen(req,timeout=180) as r:
                    raw=r.read()
                    model=str(r.headers.get('X-Rubys-Realm-Image-Model') or 'vercel-ai-gateway')
                    balance=r.headers.get('X-Rubys-Realm-Credit-Balance-Before')
                Path(dest).write_bytes(raw)
                with Image.open(dest) as im:
                    im=ImageOps.exif_transpose(im).convert('RGB')
                    if im.width<600 or im.height<600:
                        raise RuntimeError('generated illustration too small')
                    im.save(dest,quality=95)
                source={'query':str(beat)[:500],'source_type':'ai-generated-illustration','model':model,'via':'vercel-oidc-image-service','seed':seed,'visualStyle':'non-photorealistic-3d-cartoon'}
                if balance is not None:
                    try: source['creditBalanceBefore']=round(float(balance),4)
                    except Exception: pass
                SERVICE_FAILURES=0
                return source
            except Exception as e:
                last_error=e
                Path(dest).unlink(missing_ok=True)
        SERVICE_FAILURES += 1
        print('Remote cartoon generation unavailable; using local no-cost renderer:',str(last_error)[:300])
        return _procedural_cartoon(beat,seed,dest)

    def prepare_visuals(visuals,seed,_semantic_fetch=None):
        valid=[]
        for i,v in enumerate(list(visuals)):
            dest=Path(target.base.__file__).parent/'tmp'/f'v8_cartoon_{i:02d}.jpg'
            dest.parent.mkdir(parents=True,exist_ok=True)
            beat=v.get('beat_text') or v.get('query') or target.CURRENT_TITLE
            source=target._ai_image(beat,seed+i*271,dest)
            v['source']=source or {'source_type':'none','query':str(beat)[:300]}
            if dest.exists() and _is_generated(source):
                v['photo']=dest
                valid.append(v)
        visuals[:] = valid
        if len(visuals)<18:
            raise RuntimeError(f'Only {len(visuals)} generated cartoon scenes completed; refusing realistic-photo fallback')
        visuals[0]['start']=0.0
        target.base.STYLE['generated_illustration_ratio']=1.0
        target.base.STYLE['visual_source_policy']='generated-cartoon-only'
        target.base.STYLE['photographic_fallback']='disabled'
        return len(visuals)

    def select_visuals(scheduler,semantic,beats,duration):
        visuals=list(original_select(scheduler,semantic,beats,duration))
        visuals.sort(key=lambda v:float(v.get('start',0)))
        # Preserve meaningful story beats while guaranteeing the existing <=24s change-cadence QC.
        # Add the strongest unused beat near the midpoint of any oversized gap.
        def candidate_for(lo,hi):
            midpoint=(lo+hi)/2.0
            choices=[]
            for b in beats:
                st=float(b.get('start',0))
                if lo+5.0 <= st <= hi-5.0:
                    text=str(b.get('text') or '').strip()
                    if not text:
                        continue
                    score=float(b.get('score',0) or 0)
                    choices.append((abs(st-midpoint),-score,st,b))
            if not choices:
                return None
            return sorted(choices,key=lambda x:(x[0],x[1],x[2]))[0][3]

        changed=True
        while changed:
            changed=False
            visuals.sort(key=lambda v:float(v.get('start',0)))
            starts=[float(v.get('start',0)) for v in visuals]
            boundaries=list(zip(starts,starts[1:]))
            for lo,hi in boundaries:
                if hi-lo>24.0:
                    b=candidate_for(lo,hi)
                    if b is None:
                        # Deterministic midpoint split only when there is no scored scheduler beat in-range;
                        # carry the nearest narrated beat text so the illustration still matches current narration.
                        nearest=min(beats,key=lambda x:abs(float(x.get('start',0))-(lo+hi)/2.0))
                        st=(lo+hi)/2.0
                        text=str(nearest.get('text') or target.CURRENT_TITLE)
                        score=float(nearest.get('score',0) or 0)
                    else:
                        st=float(b.get('start',0)); text=str(b.get('text') or target.CURRENT_TITLE); score=float(b.get('score',0) or 0)
                    visuals.append({'start':st,'end':min(float(duration),st+8.0),'duration':8.0,'query':semantic.semantic_query(text),'score':score,'beat_text':text})
                    changed=True
                    break

        # Also prevent an oversized final hold by adding a late narrated beat when needed.
        visuals.sort(key=lambda v:float(v.get('start',0)))
        while visuals and float(duration)-float(visuals[-1].get('start',0))>24.0:
            lo=float(visuals[-1].get('start',0)); hi=float(duration)
            b=candidate_for(lo,hi)
            if b is not None:
                st=float(b.get('start',0)); text=str(b.get('text') or target.CURRENT_TITLE); score=float(b.get('score',0) or 0)
            else:
                st=min(float(duration)-6.0,lo+22.0)
                nearest=min(beats,key=lambda x:abs(float(x.get('start',0))-st))
                text=str(nearest.get('text') or target.CURRENT_TITLE); score=float(nearest.get('score',0) or 0)
            visuals.append({'start':st,'end':min(float(duration),st+8.0),'duration':8.0,'query':semantic.semantic_query(text),'score':score,'beat_text':text})
            visuals.sort(key=lambda v:float(v.get('start',0)))

        # Keep all cadence-required scenes; the normal story length keeps this comfortably bounded.
        return visuals

    def verify(video,cues,visuals,narration,source_count):
        actual,cov,gaps,ratio,checks,_passed=original_verify(video,cues,visuals,narration,source_count)
        sources=[v.get('source') or {} for v in visuals]
        generated=sum(1 for s in sources if _is_generated(s))
        generated_ratio=generated/max(1,len(visuals))
        checks['story_visual_source_ok']=all(_is_generated(s) for s in sources) and len(visuals)>=18
        checks['generated_illustration_ratio_ok']=generated_ratio==1.0 and len(visuals)>=18
        checks['no_realistic_photo_fallback_ok']=all(_is_generated(s) for s in sources)
        target.base.STYLE['generated_illustration_ratio']=round(generated_ratio,4)
        target.base.STYLE['visual_source_policy']='generated-cartoon-only'
        target.base.STYLE['photographic_fallback']='disabled'
        return actual,cov,gaps,ratio,checks,all(checks.values())

    target._ai_image=ai_image
    target.prepare_visuals=prepare_visuals
    target.select_visuals=select_visuals
    target.verify=verify
