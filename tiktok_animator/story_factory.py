import math, os, random, shutil, subprocess, textwrap, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W,H,FPS = 720,1280,12
OUT = Path('tiktok_animator/output')
TMP = Path('tiktok_animator/tmp')
OUT.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)

FONT_CANDIDATES = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'
]
FONT_PATH = next((p for p in FONT_CANDIDATES if Path(p).exists()), None)
TITLE = ImageFont.truetype(FONT_PATH, 44) if FONT_PATH else ImageFont.load_default()
CAPTION = ImageFont.truetype(FONT_PATH, 38) if FONT_PATH else ImageFont.load_default()
SMALL = ImageFont.truetype(FONT_PATH, 28) if FONT_PATH else ImageFont.load_default()

STORIES = [
    {
      'title':'The Raccoon Next Door',
      'scenes':[
        ('Mason','I knew something was wrong when the third left shoe disappeared from my porch.'),
        ('Lena','You are blaming wildlife for your laundry problem again.'),
        ('Mason','Then I checked the camera. A raccoon walked up, ignored the package, and stole exactly one blue flip-flop.'),
        ('Lena','That is weirdly specific.'),
        ('Mason','The next night I stayed awake. At 2:13 a.m., the raccoon showed up wearing a tiny reflective vest.'),
        ('Neighbor','Gary! Not the blue ones! We practiced this!'),
        ('Mason','My neighbor stepped out holding a clipboard like this was a normal training session.'),
        ('Neighbor','I can explain. The homeowners association keeps measuring porch clutter.'),
        ('Lena','So you trained a raccoon to steal shoes?'),
        ('Neighbor','Only left shoes. A matching pair counts as storage. One shoe counts as mysterious debris.'),
        ('Mason','That explanation was already insane, but then Gary came back carrying a garden gnome.'),
        ('Neighbor','No, no, no! Phase two does not start until Monday!'),
        ('Mason','Apparently phase two was removing decorations from the HOA president’s yard one item at a time.'),
        ('Lena','I should call someone.'),
        ('Mason','You should. Because Gary just rang my doorbell holding a tiny envelope with my address on it.'),
        ('Neighbor','Do not open that.'),
        ('Mason','I opened it. Inside was a handwritten invoice: one peanut per successful retrieval.'),
        ('Lena','The raccoon unionized.'),
        ('Mason','And that is how my street ended up negotiating a labor contract with a raccoon named Gary.')
      ]
    },
    {
      'title':'The Wrong Apartment',
      'scenes':[
        ('Nora','I came home and found a birthday party happening in my apartment.'),
        ('Eli','You forgot your own birthday?'),
        ('Nora','No. I did not know a single person in the room.'),
        ('Guest','Surprise, Amanda!'),
        ('Nora','My name is Nora.'),
        ('Guest','That is exactly what Amanda would say.'),
        ('Eli','You stayed, did not you?'),
        ('Nora','There was cake. I needed answers.'),
        ('Guest','Amanda, your speech!'),
        ('Nora','So I stood up and thanked everyone for supporting me through a year I had apparently never lived.'),
        ('Eli','That is when you leave.'),
        ('Nora','That is when a woman walked in screaming, Why are you all in apartment 4B?'),
        ('Guest','Amanda!'),
        ('Nora','The real Amanda lived upstairs. Everyone had the wrong floor.'),
        ('Eli','Problem solved.'),
        ('Nora','Not exactly. They had already rearranged my furniture and mounted a banner into my wall.'),
        ('Guest','We can fix that.'),
        ('Nora','They could not. The banner was covering a hole they made while trying to hang the banner.'),
        ('Eli','Please tell me you kept the cake.'),
        ('Nora','Obviously. Apartment damage fee.')
      ]
    }
]

PALETTES = [((24,29,44),(231,111,81),(244,162,97),(42,157,143)),((18,24,38),(119,141,169),(255,183,77),(239,71,111)),((32,23,41),(76,201,240),(247,37,133),(114,9,183))]


def run(cmd):
    subprocess.run(cmd, check=True)


def tts(text, voice, outwav):
    cmd=['espeak-ng','-v',voice,'-s','165','-w',str(outwav),text]
    run(cmd)


def wav_duration(path):
    with wave.open(str(path),'rb') as f:
        return f.getnframes()/float(f.getframerate())


def draw_character(draw, cx, cy, body, skin, hair, phase, speaking=False, facing=1):
    bounce = int(math.sin(phase*2*math.pi)*8)
    cy += bounce
    # legs
    draw.line((cx-25,cy+145,cx-35,cy+235), fill=body, width=20)
    draw.line((cx+25,cy+145,cx+35,cy+235), fill=body, width=20)
    # torso
    draw.rounded_rectangle((cx-72,cy+20,cx+72,cy+155), radius=26, fill=body)
    # arms gesture
    swing=int(math.sin(phase*4*math.pi)*30)
    draw.line((cx-55,cy+65,cx-115,cy+115+swing), fill=skin, width=18)
    draw.line((cx+55,cy+65,cx+115,cy+115-swing), fill=skin, width=18)
    # head
    draw.ellipse((cx-58,cy-92,cx+58,cy+24), fill=skin)
    draw.pieslice((cx-62,cy-105,cx+62,cy+10),180,360,fill=hair)
    # eyes
    eye_y=cy-42
    draw.ellipse((cx-28,eye_y-6,cx-18,eye_y+4),fill='black')
    draw.ellipse((cx+18,eye_y-6,cx+28,eye_y+4),fill='black')
    # mouth animation
    if speaking and math.sin(phase*12*math.pi)>0:
        draw.ellipse((cx-18,cy-12,cx+18,cy+16),fill=(70,20,25))
    else:
        draw.arc((cx-20,cy-10,cx+20,cy+15),0,180,fill='black',width=3)


def wrap(draw, text, font, width):
    words=text.split(); lines=[]; cur=''
    for word in words:
        test=(cur+' '+word).strip()
        if draw.textbbox((0,0),test,font=font)[2] <= width:
            cur=test
        else:
            if cur: lines.append(cur)
            cur=word
    if cur: lines.append(cur)
    return lines


def render_scene(idx, speaker, text, audio_path, palette, seed):
    dur=max(3.2,wav_duration(audio_path)+0.5)
    frames=int(dur*FPS)
    frame_dir=TMP/f'frames_{idx:02d}'
    frame_dir.mkdir(parents=True,exist_ok=True)
    rng=random.Random(seed+idx)
    bg, c1, c2, accent = palette
    for n in range(frames):
        t=n/FPS; phase=(t/dur)%1
        im=Image.new('RGB',(W,H),bg); d=ImageDraw.Draw(im)
        # simple room / street depth with movement
        d.rectangle((0,760,W,H),fill=tuple(max(0,x-12) for x in bg))
        for k in range(5):
            x=(k*180 + int(t*12)*(1 if idx%2==0 else -1))%1000-140
            d.rectangle((x,420,x+90,760),outline=accent,width=5)
            d.rectangle((x+18,455,x+42,510),fill=accent)
            d.rectangle((x+50,455,x+74,510),fill=accent)
        # characters
        speaking_left = speaker in ('Mason','Nora','Neighbor','Guest')
        draw_character(d,205,540,c1,(236,190,160),(55,38,35),phase,speaking_left)
        draw_character(d,515,550,c2,(220,166,136),(35,28,28),(phase+.25)%1,not speaking_left)
        # speaker label
        d.rounded_rectangle((38,65,330,132),radius=22,fill=(0,0,0))
        d.text((62,80),speaker,font=SMALL,fill='white')
        # captions
        box=(35,900,685,1190)
        d.rounded_rectangle(box,radius=28,fill=(0,0,0))
        lines=wrap(d,text,CAPTION,590)
        yy=930
        for line in lines[:5]:
            bbox=d.textbbox((0,0),line,font=CAPTION); tw=bbox[2]-bbox[0]
            d.text(((W-tw)/2,yy),line,font=CAPTION,fill='white')
            yy+=54
        # top progress bar
        d.rectangle((0,0,int(W*(n+1)/frames),8),fill=accent)
        im.save(frame_dir/f'{n:05d}.png')
    silent=TMP/f'scene_{idx:02d}_silent.mp4'
    out=TMP/f'scene_{idx:02d}.mp4'
    run(['ffmpeg','-y','-loglevel','error','-framerate',str(FPS),'-i',str(frame_dir/'%05d.png'),'-c:v','libx264','-pix_fmt','yuv420p','-r',str(FPS),str(silent)])
    run(['ffmpeg','-y','-loglevel','error','-i',str(silent),'-i',str(audio_path),'-c:v','copy','-c:a','aac','-shortest',str(out)])
    shutil.rmtree(frame_dir,ignore_errors=True)
    silent.unlink(missing_ok=True)
    return out


def build_story():
    story=random.choice(STORIES)
    seed=random.randint(1000,999999)
    palette=random.choice(PALETTES)
    clips=[]
    voices={'Mason':'en-us+m3','Lena':'en-us+f3','Neighbor':'en-us+m1','Nora':'en-us+f4','Eli':'en-us+m4','Guest':'en-us+f2'}
    for idx,(speaker,text) in enumerate(story['scenes']):
        wav=TMP/f'voice_{idx:02d}.wav'
        tts(text,voices.get(speaker,'en-us'),wav)
        clips.append(render_scene(idx,speaker,text,wav,palette,seed))
    concat=TMP/'concat.txt'
    concat.write_text('\n'.join([f"file '{p.resolve()}'" for p in clips]))
    safe=''.join(ch.lower() if ch.isalnum() else '-' for ch in story['title']).strip('-')
    out=OUT/f'{safe}-{seed}.mp4'
    run(['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(out)])
    print(out)

if __name__=='__main__':
    build_story()
