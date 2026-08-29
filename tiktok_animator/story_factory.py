import asyncio, hashlib, json, os, random, re, shutil, subprocess, sys, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance
import edge_tts
from story_generator import generate_story

W,H,FPS=720,1280,30
HEADER_END=int(H*.31)
VISUAL_END=int(H*.70)
OUT=Path('tiktok_animator/output')
TMP=Path('tiktok_animator/tmp')
PLAN_FILE=Path('tiktok_animator/next_story.json')
OUT.mkdir(parents=True,exist_ok=True)
TMP.mkdir(parents=True,exist_ok=True)

STYLE={
 'renderer':'reference-narration-story-v2',
 'qualityGate':'reference-photo-story-v2',
 'aspect_ratio':'9:16',
 'caption_words_max':4,
 'caption_chars_max':24,
 'visual_min_gap':8.0,
 'visual_max_gap':18.0,
 'visual_hold':[6.0,9.0],
 'visual_coverage':[.20,.44],
 'transition':.12,
 'hard_duration':[120,540],
 'target_duration':[150,420],
 'narration_wpm':[185,210],
 'minimum_external_visuals':6,
}

FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
TITLE=ImageFont.truetype(FONT,58)
PART=ImageFont.truetype(FONT,68)
SMALL=ImageFont.truetype(FONT,22)

END_BAD={'a','an','the','of','to','for','and','or','but','with','in','on','at','from','as','if','because','that','this','these','those','your','my','our','his','her','their'}
SALIENCE=set('door room key keys ledger phone camera monitor envelope photograph photo deed receipt box safe truck car vehicle desk office hallway corridor warehouse theater marina lodge diner terminal greenhouse station basement hidden locked secret missing dead died discover discovered found find open opened returns returned police sheriff deputy map survey property land road cash records file files alarm light voice stranger owner auction contract compartment'.split())


def run(cmd,capture=False):
    kw={'check':True}
    if capture: kw.update(stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    else: kw.update(stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    return subprocess.run(cmd,**kw)


def words(text):
    return re.findall(r"[A-Za-z0-9']+",text)


def safe(s):
    return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-')[:70]


def ass_escape(s):
    return str(s).replace('\\',r'\\').replace('{',r'\{').replace('}',r'\}')


def fit(draw,text,font,width):
    out=[]; cur=''
    for w in text.split():
        test=(cur+' '+w).strip()
        if draw.textbbox((0,0),test,font=font)[2] <= width:
            cur=test
        else:
            if cur: out.append(cur)
            cur=w
    if cur: out.append(cur)
    return out


def texture(draw,box,base,accent,seed):
    x0,y0,x1,y1=box
    draw.rectangle(box,fill=base)
    rng=random.Random(seed)
    for _ in range(140):
        x=rng.randint(x0,x1); y=rng.randint(y0,y1); ln=rng.randint(14,110)
        c=tuple(min(255,max(0,v+rng.randint(-10,10))) for v in base)
        draw.line((x,y,min(x1,x+ln),min(y1,y+ln)),fill=c,width=1)
    for k in range(0,x1-x0,25):
        draw.line((x0+k,y0,x0+k+175,y1),fill=accent,width=1)


def base_frame(title,part,seed):
    im=Image.new('RGB',(W,H),(10,12,15)); d=ImageDraw.Draw(im)
    texture(d,(0,0,W,HEADER_END),(14,16,19),(27,29,33),seed)
    texture(d,(0,VISUAL_END,W,H),(22,89,98),(30,111,119),seed+11)
    # Stable narration stage: deliberately restrained, not a placeholder illustration.
    for y in range(HEADER_END,VISUAL_END):
        t=(y-HEADER_END)/max(1,VISUAL_END-HEADER_END-1)
        v=int(25*(1-t)+39*t)
        d.line((0,y,W,y),fill=(v,v+2,v+5))
    for x in range(0,W,90):
        d.line((x,HEADER_END,x+180,VISUAL_END),fill=(43,45,49),width=1)
    lines=fit(d,title,TITLE,610)[:2]
    y=102 if len(lines)==2 else 146
    for line in lines:
        b=d.textbbox((0,0),line,font=TITLE,stroke_width=1); tw=b[2]-b[0]
        d.text(((W-tw)/2,y),line,font=TITLE,fill=(255,210,38),stroke_width=1,stroke_fill=(105,78,0)); y+=70
    b=d.textbbox((0,0),part,font=PART,stroke_width=1); tw=b[2]-b[0]
    d.text(((W-tw)/2,y+3),part,font=PART,fill=(82,255,24),stroke_width=1,stroke_fill=(20,90,8))
    brand="RUBY'S REALM"
    b=d.textbbox((0,0),brand,font=SMALL); tw=b[2]-b[0]
    d.text((W-tw-26,VISUAL_END+48),brand,font=SMALL,fill=(231,243,244))
    return im


def download_image(url,dest):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=90) as r:
        data=r.read()
    dest.write_bytes(data)
    return dest


def visual_frame(title,part,image_path,seed,out):
    base=base_frame(title,part,seed)
    raw=Image.open(image_path).convert('RGB')
    stage_h=VISUAL_END-HEADER_END
    fitted=ImageOps.fit(raw,(W,stage_h),method=Image.Resampling.LANCZOS,centering=(.5,.5))
    fitted=ImageEnhance.Contrast(fitted).enhance(1.04)
    fitted=ImageEnhance.Color(fitted).enhance(.96)
    base.paste(fitted,(0,HEADER_END))
    base.save(out,quality=94)


def split_beats(text):
    sentences=re.split(r'(?<=[.!?])\s+',re.sub(r'\s+',' ',text.strip()))
    out=[]; cur=[]; n=0; start=0; total=0
    for s in sentences:
        wc=len(words(s))
        if cur and n+wc>46:
            out.append({'text':' '.join(cur),'start_word':start,'word_count':n})
            start=total; cur=[]; n=0
        cur.append(s); n+=wc; total+=wc
        if n>=32:
            out.append({'text':' '.join(cur),'start_word':start,'word_count':n})
            start=total; cur=[]; n=0
    if cur: out.append({'text':' '.join(cur),'start_word':start,'word_count':n})
    return out


def beat_score(text):
    low=text.lower(); toks=set(re.findall(r'[a-z]+',low))
    score=min(8,len(toks&SALIENCE))
    if any(x in low for x in ('that night','next morning','inside','under the','behind the','suddenly','when a deputy','that afternoon','eventually','the container','the envelope')):
        score+=3
    if re.search(r'\b\d{1,4}\b',low): score+=1
    return score


def visual_prompt(text):
    clean=re.sub(r'\s+',' ',text.strip())
    return ('Cinematic photorealistic editorial still for a suspenseful vertical story video. '
            'No words, no captions, no signs with readable text, no logos, no watermark. '
            'Natural realistic lighting, believable real-world materials, atmospheric depth, intentional composition. '
            'Depict only the specific story moment described here: '+clean)


async def edge_narrate(text,audio,events_file):
    events=[]
    c=edge_tts.Communicate(text,'en-US-GuyNeural',rate='+11%')
    with open(audio,'wb') as f:
        async for chunk in c.stream():
            if chunk['type']=='audio': f.write(chunk['data'])
            elif chunk['type']=='WordBoundary':
                events.append({'text':chunk.get('text',''),'start':chunk.get('offset',0)/10000000,'duration':chunk.get('duration',0)/10000000})
    events_file.write_text(json.dumps(events,indent=2))
    return events


def duration(path):
    return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],True).stdout.strip())


def fallback_events(text,dur):
    ws=words(text); weights=[max(.7,min(2,.55+len(w)*.12)) for w in ws]
    total=sum(weights); t=0; out=[]
    for w,x in zip(ws,weights):
        d=dur*x/total; out.append({'text':w,'start':t,'duration':d}); t+=d
    return out


def fallback_tts(text,audio):
    wav=TMP/'fallback.wav'
    run(['espeak-ng','-v','en-us+m3','-s','190','-w',str(wav),text])
    run(['ffmpeg','-y','-loglevel','error','-i',str(wav),'-c:a','libmp3lame','-b:a','128k',str(audio)])
    return fallback_events(text,duration(audio))


def captions(events):
    out=[]; i=0
    while i<len(events):
        start=i; chunk=[]; chars=0
        while i<len(events) and len(chunk)<STYLE['caption_words_max']:
            w=str(events[i].get('text','')).strip()
            if not w: i+=1; continue
            add=len(w)+(1 if chunk else 0)
            if chunk and chars+add>STYLE['caption_chars_max']: break
            chunk.append(w); chars+=add; i+=1
            if i<len(events):
                gap=events[i]['start']-(events[i-1]['start']+max(events[i-1].get('duration',.1),.1))
                if len(chunk)>=2 and gap>.16: break
        # Avoid ugly fragments ending on glue words when one more word fits.
        if chunk and chunk[-1].lower().strip(".,!?:;'\"") in END_BAD and i<len(events) and len(chunk)<STYLE['caption_words_max']:
            nxt=str(events[i].get('text','')).strip()
            if chars+1+len(nxt)<=STYLE['caption_chars_max']:
                chunk.append(nxt); i+=1
        if not chunk:
            i=max(i,start+1); continue
        a=events[start]['start']; e=events[i-1]
        b=e['start']+max(e.get('duration',.12),.12)
        if i<len(events): b=min(b,events[i]['start']-.01)
        out.append({'start':a,'end':max(a+.18,b),'text':' '.join(chunk).upper(),'words':len(chunk)})
    return out


def atime(sec):
    h=int(sec//3600); m=int((sec%3600)//60); s=sec%60
    return f'{h}:{m:02d}:{s:05.2f}'


def write_ass(cues,path):
    head=(f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
          "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
          "Style: Caption,DejaVu Sans,52,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,2,92,92,448,1\n\n"
          "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    lines=[head]
    for c in cues:
        lines.append(f"Dialogue: 0,{atime(c['start'])},{atime(c['end'])},Caption,,0,0,0,,{{\\an2\\fscx110\\fscy110\\t(0,90,\\fscx100\\fscy100)}}{ass_escape(c['text'])}\n")
    path.write_text(''.join(lines))


def time_beats(beats,events,dur):
    total_words=max(1,sum(b['word_count'] for b in beats)); n=len(events)
    for b in beats:
        if n:
            a=min(n-1,round((b['start_word']/total_words)*(n-1)))
            end=b['start_word']+b['word_count']
            z=min(n-1,round((end/total_words)*(n-1)))
            b['start']=events[a]['start']
            b['end']=min(dur,events[z]['start']+max(events[z].get('duration',.1),.1))
        else:
            b['start']=dur*b['start_word']/total_words
            b['end']=dur*(b['start_word']+b['word_count'])/total_words
        b['score']=beat_score(b['text'])
        b['prompt']=visual_prompt(b['text'])
    return beats


def choose_visual_beats(beats,dur):
    selected=[]; last=-99.0
    for idx,b in enumerate(beats):
        gap=b['start']-last
        pick=(idx==0 or gap>=STYLE['visual_max_gap'] or (gap>=STYLE['visual_min_gap'] and b['score']>=4))
        if pick:
            hold=min(STYLE['visual_hold'][1],max(STYLE['visual_hold'][0],min((b['end']-b['start'])+1.2,STYLE['visual_hold'][1])))
            if b['start']+hold<dur-.2:
                selected.append({'beat_index':idx,'start':b['start'],'end':b['start']+hold,'duration':hold,'score':b['score'],'prompt':b['prompt'],'beat_text':b['text']})
                last=b['start']
    return selected


def load_plan():
    if not PLAN_FILE.exists(): return None
    try: return json.loads(PLAN_FILE.read_text())
    except Exception: return None


def bind_external_visuals(selected,plan):
    supplied=(plan or {}).get('visuals') or []
    by_beat={int(v['beat_index']):v for v in supplied if isinstance(v,dict) and str(v.get('beat_index','')).isdigit() and v.get('url')}
    out=[]
    for v in selected:
        ext=by_beat.get(v['beat_index'])
        if not ext: continue
        item=dict(v)
        item['url']=ext['url']
        item['clean_text']=bool(ext.get('clean_text',False))
        item['visual_source']=ext.get('source','generated-external')
        out.append(item)
    return out


def render(base,visuals,audio,ass,dur,out):
    cmd=['ffmpeg','-y','-loglevel','error','-loop','1','-framerate',str(FPS),'-t',str(dur),'-i',str(base)]
    for v in visuals:
        cmd += ['-loop','1','-framerate',str(FPS),'-t',str(v['duration']),'-i',str(v['frame'])]
    audio_index=1+len(visuals)
    cmd += ['-i',str(audio)]
    filters=[f'[0:v]scale={W}:{H},format=yuv420p[base]']; cur='base'; fade=STYLE['transition']
    for i,v in enumerate(visuals,1):
        label=f'v{i}'; st=v['start']; en=v['end']; d=max(v['duration'],fade*2+.1)
        filters.append(f'[{i}:v]scale={W}:{H},format=rgba,fade=t=in:st=0:d={fade}:alpha=1,fade=t=out:st={max(0,d-fade):.3f}:d={fade}:alpha=1,setpts=PTS+{st:.3f}/TB[ov{i}]')
        filters.append(f'[{cur}][ov{i}]overlay=0:0:enable=\'between(t,{st:.3f},{en:.3f})\'[{label}]')
        cur=label
    ap=str(ass).replace(':','\\:').replace("'",r"\'")
    filters.append(f'[{cur}]ass=\'{ap}\'[vout]')
    cmd += ['-filter_complex',';'.join(filters),'-map','[vout]','-map',f'{audio_index}:a','-af','loudnorm=I=-14:TP=-1.0:LRA=7','-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p','-r',str(FPS),'-c:a','aac','-b:a','160k','-movflags','+faststart','-t',str(dur),str(out)]
    run(cmd)


def verify(video,cues,visuals,narration,story_id,generated_story):
    actual=duration(video)
    coverage=sum(v['duration'] for v in visuals)/max(1,actual)
    starts=[v['start'] for v in visuals]
    gaps=[b-a for a,b in zip(starts,starts[1:])]
    checks={
        'duration_in_range':STYLE['hard_duration'][0] <= actual <= STYLE['hard_duration'][1],
        'new_story_id_present':bool(story_id),
        'generated_story':bool(generated_story),
        'caption_density_ok':len(cues)>=100,
        'caption_word_limit_ok':max((c['words'] for c in cues),default=0)<=STYLE['caption_words_max'],
        'external_visual_count_ok':len(visuals)>=STYLE['minimum_external_visuals'],
        'external_visuals_clean_text':bool(visuals) and all(v.get('clean_text') for v in visuals),
        'visual_coverage_ok':STYLE['visual_coverage'][0]-.06 <= coverage <= STYLE['visual_coverage'][1]+.03,
        'visual_spacing_ok':not gaps or min(gaps)>=6.5,
        'audio_video_sync_ok':abs(actual-narration)<=2,
    }
    return actual,coverage,gaps,checks,all(checks.values())


def main():
    for p in TMP.glob('*'):
        p.unlink() if p.is_file() else shutil.rmtree(p,ignore_errors=True)
    for p in OUT.glob('*'):
        p.unlink() if p.is_file() else shutil.rmtree(p,ignore_errors=True)

    seed=int(os.getenv('STORY_SEED',str(random.randint(10000,999999))))
    plan=load_plan()
    generated=generate_story(seed)
    story=os.getenv('STORY_TEXT','').strip() or (plan or {}).get('story') or generated['story']
    title=os.getenv('STORY_TITLE','').strip() or (plan or {}).get('title') or generated['title']
    part=os.getenv('STORY_PART','').strip() or (plan or {}).get('part') or generated['part']
    story_id=(plan or {}).get('story_id') or generated['story_id'] or hashlib.sha256(story.encode()).hexdigest()[:16]
    generated_story=not bool(os.getenv('STORY_TEXT','').strip())

    audio=TMP/'narration.mp3'; boundaries=TMP/'word-boundaries.json'
    try:
        events=asyncio.run(edge_narrate(story,audio,boundaries))
        if len(events)<50: raise RuntimeError('insufficient word boundaries')
    except Exception as e:
        print('edge narration fallback:',e,file=sys.stderr)
        events=fallback_tts(story,audio)
        boundaries.write_text(json.dumps(events,indent=2))

    dur=duration(audio)
    cues=captions(events)
    beats=time_beats(split_beats(story),events,dur)
    selected=choose_visual_beats(beats,dur)
    visuals=bind_external_visuals(selected,plan)

    base=TMP/'base.png'
    base_frame(title,part,seed).save(base,quality=94)
    for i,v in enumerate(visuals):
        raw=TMP/f'raw_{i:02d}.img'
        frame=TMP/f'visual_{i:02d}.jpg'
        download_image(v['url'],raw)
        visual_frame(title,part,raw,seed+i*131,frame)
        v['frame']=frame

    ass=TMP/'captions.ass'; write_ass(cues,ass)
    name=f'{safe(title)}-{story_id}-{seed}'
    video=OUT/f'{name}.mp4'
    render(base,visuals,audio,ass,dur,video)
    actual,cov,gaps,checks,passed=verify(video,cues,visuals,dur,story_id,generated_story)

    manifest={
        'renderer':STYLE['renderer'],'qualityGate':STYLE['qualityGate'],'qualityPassed':passed,
        'title':title,'part':part,'storyId':story_id,'generatedStory':generated_story,'file':video.name,
        'durationSeconds':round(actual,3),'narrationSeconds':round(dur,3),'captionCueCount':len(cues),
        'captionMaxWords':max((c['words'] for c in cues),default=0),'visualInsertCount':len(visuals),
        'visualCoverageRatio':round(cov,4),'visualMinGap':round(min(gaps),3) if gaps else None,
        'style':STYLE,'checks':checks,
        'visuals':[{k:(round(x,3) if isinstance(x,float) else x) for k,x in v.items() if k not in ('frame','url')} for v in visuals],
        'neededVisualPrompts':[{'beat_index':v['beat_index'],'prompt':v['prompt'],'beat_text':v['beat_text']} for v in selected],
    }
    (OUT/f'{name}.json').write_text(json.dumps(manifest,indent=2))
    if not passed:
        print(json.dumps(manifest,indent=2),file=sys.stderr)
        raise RuntimeError('Quality gate failed; refusing to publish low-quality output')
    print(video)

if __name__=='__main__':
    main()
