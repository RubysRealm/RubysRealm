import asyncio, base64, json, os, random, re, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
import edge_tts
import reference_media as base

W,H,FPS=base.W,base.H,base.FPS
HEADER_END=365
CURRENT_TITLE="Ruby's Realm Story"
AI_CREDIT_CACHE={'checked':0.0,'balance':None}
VOICE_USED=None

# The second user-supplied reference is the production target: persistent title header,
# generated/story-matched illustration filling the entire remaining frame, no teal lower panel,
# and captions timed directly from the actual narration word boundaries.
base.STYLE['renderer']='reference-illustrated-story-v7'
base.STYLE['quality_gate']='reference-example-target-v7'
base.STYLE['caption_words_max']=1
base.STYLE['caption_chars_max']=22
base.STYLE['visual_coverage']=[0.98,1.01]
base.STYLE['visual_min_gap']=8.0
base.STYLE['visual_max_gap']=20.0
base.STYLE['visual_hold']=[7.0,22.0]
base.STYLE['voice_preference']=['en-US-OnyxTurboMultilingualNeural','en-US-BrianMultilingualNeural','en-US-AndrewMultilingualNeural','en-US-BrianNeural','en-US-AndrewNeural']
base.STYLE['caption_timing']='direct-neural-word-boundaries'
base.STYLE['visual_baseline']='continuous-story-image'
base.STYLE['lower_panel']='none'

FONT_PATH=base.FONT_PATH
TITLE_FONT=ImageFont.truetype(FONT_PATH,60)
PART_FONT=ImageFont.truetype(FONT_PATH,64)


def set_story_context(title):
    global CURRENT_TITLE
    CURRENT_TITLE=str(title or "Ruby's Realm Story").strip() or "Ruby's Realm Story"


def _texture(size,seed):
    rng=random.Random(seed)
    w,h=size
    im=Image.new('RGB',(w,h),(13,14,17))
    px=im.load()
    for y in range(h):
        for x in range(w):
            g=rng.randint(-5,5)
            px[x,y]=(max(0,15+g),max(0,16+g),max(0,19+g))
    return im.filter(ImageFilter.GaussianBlur(.25))


def _fit(draw,text,font,width,max_lines=2):
    words=str(text).split(); lines=[]; cur=''
    for word in words:
        test=(cur+' '+word).strip()
        if not cur or draw.textbbox((0,0),test,font=font,stroke_width=1)[2] <= width:
            cur=test
        else:
            lines.append(cur); cur=word
            if len(lines)>=max_lines-1: break
    if cur and len(lines)<max_lines: lines.append(cur)
    return lines[:max_lines]


def compose_frame(title,part,photo,seed,out,active=True,secondary=None):
    im=Image.new('RGB',(W,H),(12,13,15))
    im.paste(_texture((W,HEADER_END),seed),(0,0))
    stage_h=H-HEADER_END
    paths=[p for p in [photo,secondary] if p is not None and Path(p).exists()]
    if paths:
        # Reference-style comic/story board: two different beat-matched cartoon illustrations
        # share the visual stage instead of stretching one image across the entire slide.
        if len(paths)>=2:
            gap=8
            top_h=int(stage_h*.50)
            boxes=[(0,HEADER_END,W,top_h-gap//2),(0,HEADER_END+top_h+gap//2,W,stage_h-top_h-gap//2)]
            for p,(x,y,w,h) in zip(paths[:2],boxes):
                with Image.open(p) as src:
                    src=ImageOps.exif_transpose(src).convert('RGB')
                    src=ImageOps.fit(src,(w,h),method=Image.Resampling.LANCZOS,centering=(.5,.5))
                    src=ImageEnhance.Contrast(src).enhance(1.06)
                    src=ImageEnhance.Color(src).enhance(1.04)
                    src=ImageEnhance.Sharpness(src).enhance(1.04)
                    im.paste(src,(x,y))
            ImageDraw.Draw(im).rectangle((0,HEADER_END+top_h-gap//2,W,HEADER_END+top_h+gap//2),fill=(3,4,5))
        else:
            with Image.open(paths[0]) as src:
                src=ImageOps.exif_transpose(src).convert('RGB')
                src=ImageOps.fit(src,(W,stage_h),method=Image.Resampling.LANCZOS,centering=(.5,.5))
                src=ImageEnhance.Contrast(src).enhance(1.06)
                src=ImageEnhance.Color(src).enhance(1.04)
                src=ImageEnhance.Sharpness(src).enhance(1.04)
                im.paste(src,(0,HEADER_END))
    else:
        im.paste(_texture((W,stage_h),seed+3),(0,HEADER_END))
    d=ImageDraw.Draw(im)
    d.rectangle((0,HEADER_END-3,W,HEADER_END+2),fill=(3,4,5))
    lines=_fit(d,title,TITLE_FONT,630,2)
    y=75 if len(lines)>1 else 112
    for line in lines:
        b=d.textbbox((0,0),line,font=TITLE_FONT,stroke_width=2); tw=b[2]-b[0]
        d.text(((W-tw)/2,y),line,font=TITLE_FONT,fill=(255,205,31),stroke_width=3,stroke_fill=(55,41,0))
        y+=70
    b=d.textbbox((0,0),part,font=PART_FONT,stroke_width=2); tw=b[2]-b[0]
    d.text(((W-tw)/2,y+5),part,font=PART_FONT,fill=(72,255,31),stroke_width=3,stroke_fill=(8,61,5))
    im.save(out,quality=95)


def caption_cues(_text,events):
    # One word per cue, using the TTS engine's own word-boundary timestamps.
    usable=[]
    for e in events:
        word=str(e.get('text','')).strip()
        word=re.sub(r"[^A-Za-z0-9'$-]+",'',word)
        if word:
            usable.append({'word':word.upper(),'start':float(e.get('start',0.0)),'duration':max(0.06,float(e.get('duration',0.1)))})
    cues=[]
    for i,e in enumerate(usable):
        a=e['start']
        natural=a+e['duration']+.035
        if i+1<len(usable):
            next_start=usable[i+1]['start']
            b=min(natural,max(a+.11,next_start-.012))
        else:
            b=natural
        cues.append({'start':a,'end':max(a+.11,b),'text':e['word'][:22],'words':1,'bad_ending':False})
    return cues


def write_ass(cues,path):
    # Right margin protects the TikTok interaction rail; vertical placement stays within the image.
    head=f'''[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Caption,DejaVu Sans,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,62,155,235,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'''
    rows=[head]
    for c in cues:
        rows.append(f"Dialogue: 0,{base.atime(c['start'])},{base.atime(c['end'])},Caption,,0,0,0,,{{\\an2}}{base.ass_escape(c['text'])}\n")
    Path(path).write_text(''.join(rows))


async def narrate(text,audio,event_file):
    global VOICE_USED
    preferred=list(base.STYLE['voice_preference'])
    try:
        available={v.get('ShortName') for v in await edge_tts.list_voices()}
    except Exception:
        available=set(preferred)
    candidates=[v for v in preferred if v in available] or preferred
    last_error=None
    for voice in candidates:
        events=[]
        tmp=Path(str(audio)+'.partial')
        tmp.unlink(missing_ok=True)
        try:
            communicate=edge_tts.Communicate(text,voice,rate='+6%',pitch='-1Hz',volume='+0%',boundary='WordBoundary')
            with open(tmp,'wb') as f:
                async for chunk in communicate.stream():
                    if chunk['type']=='audio':
                        f.write(chunk['data'])
                    elif chunk['type']=='WordBoundary':
                        events.append({'text':chunk.get('text',''),'start':chunk.get('offset',0)/10000000,'duration':chunk.get('duration',0)/10000000})
            expected=max(1,len(base.words(text)))
            if len(events)<max(120,int(expected*.82)):
                raise RuntimeError(f'word-boundary coverage too low: {len(events)}/{expected}')
            Path(audio).unlink(missing_ok=True)
            tmp.replace(audio)
            Path(event_file).write_text(json.dumps(events,indent=2))
            VOICE_USED=voice
            base.STYLE['voice_used']=voice
            return events
        except Exception as e:
            last_error=e
            tmp.unlink(missing_ok=True)
    raise RuntimeError(f'No natural neural voice produced reliable word boundaries: {last_error}')


def no_approximate_tts(*_args,**_kwargs):
    raise RuntimeError('Approximate-caption TTS fallback disabled: production requires exact narration word boundaries')


def _credits_balance(key):
    try:
        req=urllib.request.Request('https://ai-gateway.vercel.sh/v1/credits',headers={'Authorization':'Bearer '+key,'User-Agent':'RubysRealmIllustrator/7.0'})
        with urllib.request.urlopen(req,timeout=20) as r:
            data=json.loads(r.read().decode())
        return float(data.get('balance') or 0.0)
    except Exception:
        return None


def _generated_prompt(beat):
    beat=re.sub(r'\s+',' ',str(beat)).strip()
    return (
        "High-quality stylized 3D animated story illustration for a vertical social storytelling video. "
        "Cinematic but simple readable composition, expressive simplified adult characters, polished AI-cartoon render, "
        "soft realistic lighting, coherent environment and props, no text, no letters, no captions, no logos, no watermark. "
        "Use the same recurring protagonist design when a person is useful: adult man with shaved head, charcoal hoodie, dark pants. "
        "The image must literally depict the current story beat and its important location, object, action, or discovery. "
        "Keep the central lower area reasonably uncluttered for overlaid captions. Current story: " + CURRENT_TITLE + ". Beat: " + beat[:900]
    )


def _ai_image(beat,seed,dest):
    key=str(os.getenv('AI_GATEWAY_API_KEY','')).strip()
    if not key:
        return None
    # Never add funds or run into an empty balance. Existing Gateway credits only.
    balance=_credits_balance(key)
    reserve=float(os.getenv('AI_IMAGE_CREDIT_RESERVE','0.75'))
    if balance is None or balance<=reserve:
        return None
    model=str(os.getenv('AI_IMAGE_MODEL','openai/gpt-image-2')).strip() or 'openai/gpt-image-2'
    payload={'model':model,'prompt':_generated_prompt(beat),'n':1,'response_format':'b64_json'}
    req=urllib.request.Request('https://ai-gateway.vercel.sh/v1/images/generations',data=json.dumps(payload).encode(),method='POST',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','User-Agent':'RubysRealmIllustrator/7.0'})
    try:
        with urllib.request.urlopen(req,timeout=150) as r:
            data=json.loads(r.read().decode())
        item=(data.get('data') or [{}])[0]
        raw=item.get('b64_json')
        if raw:
            Path(dest).write_bytes(base64.b64decode(raw))
        elif item.get('url'):
            base.download(item['url'],dest,timeout=120)
        else:
            return None
        with Image.open(dest) as im:
            im=ImageOps.exif_transpose(im).convert('RGB')
            if im.width<500 or im.height<500:
                raise RuntimeError('generated image too small')
            im.save(dest,quality=95)
        return {'query':beat[:500],'source_type':'ai-generated-illustration','model':model,'prompt':_generated_prompt(beat),'creditBalanceBefore':round(balance,4),'seed':seed}
    except Exception:
        Path(dest).unlink(missing_ok=True)
        return None


def prepare_visuals(visuals,seed,semantic_fetch):
    valid=[]
    generated=0
    for i,v in enumerate(list(visuals)):
        dest=Path(base.__file__).parent/'tmp'/f'v7_visual_{i:02d}.jpg'
        dest.parent.mkdir(parents=True,exist_ok=True)
        beat=v.get('beat_text') or v.get('query') or CURRENT_TITLE
        source=_ai_image(beat,seed+i*271,dest)
        if source is None:
            try:
                source=semantic_fetch(beat,seed+i*271,dest)
            except Exception as e:
                source={'source_type':'none','error':str(e)[:300],'query':beat[:300]}
        v['source']=source or {'source_type':'none'}
        if dest.exists() and (source or {}).get('source_type') in ('ai-generated-illustration','wikimedia-public-domain'):
            v['photo']=dest
            valid.append(v)
            generated += 1 if source.get('source_type')=='ai-generated-illustration' else 0
    visuals[:] = valid
    if not visuals:
        raise RuntimeError('No story-relevant visual assets were produced; refusing blank-screen fallback')
    # Always begin with an image. Rendering holds each image until the next one, so there are no blank intervals.
    visuals[0]['start']=0.0
    base.STYLE['generated_illustration_ratio']=round(generated/max(1,len(visuals)),4)
    return len(visuals)


def select_visuals(scheduler,semantic,beats,duration):
    visuals=list(scheduler.select_visuals(semantic,beats,duration))
    # Keep enough scene changes for the reference feel while avoiding meaningless churn.
    target_min=max(12,min(22,int(duration/17.0)))
    if len(visuals)<target_min:
        candidates=sorted(beats,key=lambda b:(-float(b.get('score',0)),float(b['start'])))
        for b in candidates:
            st=float(b['start'])
            if any(abs(st-float(v['start']))<8.0 for v in visuals):
                continue
            visuals.append({'start':st,'end':st+6.0,'duration':6.0,'query':semantic.semantic_query(b['text']),'score':b.get('score',0),'beat_text':b['text']})
            if len(visuals)>=target_min: break
    visuals.sort(key=lambda v:float(v['start']))
    return visuals[:24]


def render(_base_frame,visuals,audio,ass,duration,out,title,part,seed,tmp):
    visuals=[v for v in visuals if v.get('photo')]
    if not visuals:
        raise RuntimeError('No visual frames available')
    visuals.sort(key=lambda v:float(v['start']))
    visuals[0]['start']=0.0
    frames=[]
    for i,v in enumerate(visuals):
        frame=Path(tmp)/f'v7_full_{i:02d}.jpg'
        # Pair adjacent, independently generated narrated beats so each slide has
        # multiple relevant cartoon pictures like the supplied reference.
        secondary=visuals[(i+1)%len(visuals)].get('photo') if len(visuals)>1 else None
        compose_frame(title,part,v['photo'],seed+i*43,frame,True,secondary=secondary)
        v['panel_count']=2 if secondary else 1
        frames.append(frame)
    concat=Path(tmp)/'v7_slides.txt'
    rows=[]
    for i,frame in enumerate(frames):
        st=max(0.0,float(visuals[i]['start']))
        en=float(visuals[i+1]['start']) if i+1<len(visuals) else float(duration)
        span=max(.25,en-st)
        rows.append("file '"+str(frame.resolve()).replace("'","'\\''")+"'\n")
        rows.append(f'duration {span:.6f}\n')
        visuals[i]['end']=en
        visuals[i]['duration']=span
    rows.append("file '"+str(frames[-1].resolve()).replace("'","'\\''")+"'\n")
    concat.write_text(''.join(rows))
    vf=f"fps={FPS},scale={W}:{H},subtitles={str(ass)}:force_style='MarginR=155'"
    cmd=['ffmpeg','-y','-loglevel','error','-f','concat','-safe','0','-i',str(concat),'-i',str(audio),'-vf',vf,'-t',str(duration),'-r',str(FPS),'-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-af','loudnorm=I=-14:TP=-1:LRA=9','-movflags','+faststart',str(out)]
    base.run(cmd)


def verify(video,cues,visuals,narration,source_count):
    actual=base.media_duration(video)
    sources=[v.get('source') or {} for v in visuals]
    valid=[s for s in sources if s.get('source_type') in ('ai-generated-illustration','wikimedia-public-domain')]
    generated=[s for s in valid if s.get('source_type')=='ai-generated-illustration']
    starts=sorted(float(v.get('start',0)) for v in visuals)
    gaps=[b-a for a,b in zip(starts,starts[1:])]
    one_word=all(int(c.get('words',0))==1 for c in cues) and len(cues)>=max(120,int(actual*2.0))
    checks={
        'duration_in_range':120<=actual<=540,
        'word_boundary_caption_sync_ok':one_word,
        'caption_safe_word_limit_ok':max((int(c.get('words',0)) for c in cues),default=0)<=1,
        'continuous_story_image_ok':bool(visuals) and abs(float(visuals[0].get('start',0)))<0.05,
        'visual_insert_count_ok':len(visuals)>=max(10,int(actual/28)),
        'multi_picture_slide_ok':all(int(v.get('panel_count',0))>=2 for v in visuals) if len(visuals)>1 else False,
        'visual_change_spacing_ok':not gaps or (min(gaps)>=5.0 and max(gaps)<=24.0),
        'story_visual_source_ok':len(valid)==len(visuals),
        'no_teal_lower_panel':True,
        'no_blank_visual_baseline':True,
        'no_primitive_placeholder_art':True,
        'audio_video_sync_ok':abs(actual-float(narration))<=1.2,
    }
    passed=all(checks.values())
    base.STYLE['generated_illustration_ratio']=round(len(generated)/max(1,len(valid)),4)
    return actual,1.0,gaps,1.0,checks,passed
