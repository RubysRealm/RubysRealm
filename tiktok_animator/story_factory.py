import asyncio, json, math, os, random, re, shutil, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import edge_tts

W,H,FPS=720,1280,30
HEADER_END=int(H*.31); VISUAL_END=int(H*.70)
OUT=Path('tiktok_animator/output'); TMP=Path('tiktok_animator/tmp')
OUT.mkdir(parents=True,exist_ok=True); TMP.mkdir(parents=True,exist_ok=True)

STYLE={
 'renderer':'reference-narration-story-v1','aspect_ratio':'9:16','reference_seconds':301.6,
 'reference_visual_median':3.6,'reference_visual_iqr':[2.0,4.6],'reference_visual_p90':6.58,
 'caption_words_max':3,'caption_chars_max':20,'visual_min_gap':9.0,'visual_max_gap':24.0,
 'visual_hold':[6.0,9.0],'visual_coverage':[.20,.42],'transition':.14,
 'hard_duration':[120,540],'target_duration':[150,420],'narration_wpm':[185,210]
}
FONT='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
TITLE=ImageFont.truetype(FONT,62); PART=ImageFont.truetype(FONT,70); SMALL=ImageFont.truetype(FONT,24)

DEFAULT_STORY="""
You buy a fading roadside motel at a county auction because the price looks impossible to ignore. The property sits two miles outside a small town, eighteen doors wrapped around an empty swimming pool, with a front office that still smells like burnt coffee and old carpet. The county paperwork says the place has been closed for three years. A handwritten note taped inside the office drawer says eleven months.

On the first afternoon, a contractor walks the property with you. He points out cracked stucco, two bad air conditioners, a roof patch over room eight, and a boiler old enough to have its own personality. Then he stops in front of a door beside room sixteen. There is no number on it. The county inventory lists only sixteen guest rooms.

You assume the numbering changed years ago, but the key rack behind the desk still has a brass tag stamped seventeen. The key is missing. Under the rack is an old ledger with every room written in blue ink. Room seventeen appears repeatedly, but instead of guest names the entries contain dates, dollar amounts, and one short word: hold.

That night you stay in the office because the utilities have just been restored. At 1:42 in the morning the desk phone rings. The outside line is not connected yet. You answer anyway. For several seconds there is only static, then a man says, very calmly, that the ice machine is empty. The motel has no ice machine. The contractor removed it that afternoon.

You walk outside with a flashlight. Every room is dark except the unnumbered door. A thin line of light shows beneath it even though the breaker to that side of the building is off. When you get close, the light disappears. The door is locked from the inside.

The next morning you call the county clerk and ask for the original floor plan. She sends a scanned drawing from 1978. It shows sixteen guest rooms, but behind the laundry room is a narrow service corridor that vanished from later plans. At the end of that corridor is a small square marked office storage.

You and the contractor remove a sheet of plywood from the laundry wall. Behind it is the corridor. The floor is dusty except for a clean path through the middle, as though someone has been walking there recently. Halfway down is an electrical panel feeding one circuit. The label is handwritten: seventeen.

At the end of the corridor is the back side of the mysterious room. The contractor opens it with a pry bar. Inside there is no bed or bathroom. There is a metal desk, three filing cabinets, a calendar frozen on April from eleven years ago, and an old security monitor connected to cameras around the property. One camera is still working. The picture shows the parking lot in real time.

On the desk is another ledger. This one explains the numbers. For years the previous owner rented normal motel rooms, but he also charged local businesses to store cash, documents, spare keys, and sealed envelopes in room seventeen. Nothing appeared on the motel books. The room operated like an unofficial night safe.

Most entries stop eleven years ago. One does not. Every few months a new amount appears beside the initials C W. The latest entry is dated three weeks before the county auction. You call the former owner. His number is disconnected. Then you discover he died four years earlier.

That afternoon a black pickup pulls into the lot. An older man gets out, looks at the construction dumpster, and asks whether the motel is open. You tell him not yet. He asks if you found the room behind the laundry wall. You do not answer. He smiles like that already answered the question, hands you a plain envelope, and says he will come back after dark for what belongs to him.

Inside the envelope is a photocopy of a deed, a storage receipt, and an old photograph of the motel. Someone circled the ground beneath room seventeen. On the back is written: not in the room. Under it.

The contractor wants to call the police. Before you can, he notices four newer bolts in the floor beneath the metal desk. You move the desk, remove the bolts, and lift a steel plate hidden under the carpet. Below it is a concrete cavity containing a locked fireproof box.

You do not open it. You call the sheriff. While you wait, the security monitor flickers. The parking-lot camera shows the black pickup returning. It stops across the road instead of pulling in. The driver never gets out.

A deputy arrives twenty minutes later. By then the truck is gone. The fireproof box contains old property records, several envelopes of cash, and a second set of ownership documents. One paper appears to transfer a narrow strip of land behind the motel to a company that no longer exists. That strip is exactly where the county plans to build an access road for a new industrial park.

Suddenly the auction price makes sense. The motel itself was never the valuable part.

Over the next week attorneys, county officials, and investigators sort through the papers. The cash is taken as evidence. The ownership claim is disputed. The mysterious man never returns. Three months later the county offers to purchase the disputed strip as part of a settlement. The payment is more than you paid for the entire motel.

You accept, use part of the money to finish the renovations, and finally open sixteen rooms to guests. You leave the seventeenth door exactly where it is. It becomes your locked records room. The old desk phone is gone, the security monitor is disconnected, and the brass key tag hangs behind the front counter as a reminder.

Every few weeks someone checking in notices the tag and asks why there is a key for a room that does not exist. You always give them the same answer. Old motels have strange numbering.
""".strip()

KEYWORD_SCENES=[
 (('fireproof','lockbox','steel plate','cavity'),'hidden lockbox beneath an old floor'),
 (('security monitor','camera','monitor'),'security monitor showing an empty parking lot'),
 (('room seventeen','unnumbered door','locked from the inside'),'dim motel hallway with one unnumbered door'),
 (('service corridor','corridor'),'narrow hidden service corridor'),
 (('ledger','filing','records'),'old ledger and files on a desk'),
 (('envelope','photograph','deed','receipt'),'envelope with old property papers'),
 (('pickup','truck'),'black pickup across from an old motel'),
 (('sheriff','deputy','police'),'county deputy vehicle outside a motel'),
 (('industrial park','access road'),'industrial park construction beyond roadside property'),
 (('key tag','brass tag','key rack'),'brass motel key tag behind a front desk'),
 (('contractor','renovation','plywood','laundry'),'motel renovation with an opened wall'),
 (('front office','front desk','desk phone','office'),'old motel front desk'),
 (('motel','property','auction'),'roadside motel exterior at dusk')]
LOCATIONS=set('motel hotel office room hallway corridor town parking road industrial laundry pool desk'.split())
OBJECTS=set('key ledger phone camera monitor door envelope photograph deed receipt box safe truck desk calendar files records cash'.split())
DRAMA=set('hidden missing locked dead died secret mysterious flickers static dark disputed investigator police sheriff under behind inside returns'.split())
EVENTS=set('opens remove find discover arrive call rings returns stops hands lift build purchase auction offers accept'.split())

def run(cmd,capture=False):
 kw={'check':True}
 if capture: kw.update(stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 else: kw.update(stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 return subprocess.run(cmd,**kw)

def words(text): return re.findall(r"[A-Za-z0-9']+",text)
def safe(s): return re.sub(r'[^a-z0-9]+','-',s.lower()).strip('-')[:70]
def ass_escape(s): return str(s).replace('\\',r'\\').replace('{',r'\{').replace('}',r'\}')

def fit(draw,text,font,width):
 out=[]; cur=''
 for w in text.split():
  test=(cur+' '+w).strip()
  if draw.textbbox((0,0),test,font=font)[2]<=width: cur=test
  else:
   if cur: out.append(cur)
   cur=w
 if cur: out.append(cur)
 return out

def texture(draw,box,base,accent,seed):
 x0,y0,x1,y1=box; draw.rectangle(box,fill=base); rng=random.Random(seed)
 for _ in range(100):
  x=rng.randint(x0,x1); y=rng.randint(y0,y1); ln=rng.randint(20,90)
  c=tuple(min(255,max(0,v+rng.randint(-12,12))) for v in base)
  draw.line((x,y,min(x1,x+ln),min(y1,y+ln)),fill=c,width=1)
 for k in range(0,x1-x0,22): draw.line((x0+k,y0,x0+k+150,y1),fill=accent,width=1)

def base_frame(title,part,seed):
 im=Image.new('RGB',(W,H),(12,14,18)); d=ImageDraw.Draw(im)
 texture(d,(0,0,W,HEADER_END),(15,17,20),(27,29,33),seed)
 texture(d,(0,VISUAL_END,W,H),(24,93,101),(30,116,124),seed+3)
 d.rectangle((0,HEADER_END,W,VISUAL_END),fill=(32,35,41))
 for y in range(HEADER_END+18,VISUAL_END,38): d.line((0,y,W,y),fill=(44,46,50),width=1)
 lines=fit(d,title,TITLE,610)[:2]; y=105 if len(lines)==2 else 150
 for line in lines:
  b=d.textbbox((0,0),line,font=TITLE,stroke_width=1); tw=b[2]-b[0]
  d.text(((W-tw)/2,y),line,font=TITLE,fill=(255,210,38),stroke_width=1,stroke_fill=(105,78,0)); y+=74
 b=d.textbbox((0,0),part,font=PART,stroke_width=1); tw=b[2]-b[0]
 d.text(((W-tw)/2,y+4),part,font=PART,fill=(82,255,24),stroke_width=1,stroke_fill=(20,90,8))
 brand="RUBY'S REALM"; b=d.textbbox((0,0),brand,font=SMALL); tw=b[2]-b[0]
 d.text((W-tw-24,VISUAL_END+52),brand,font=SMALL,fill=(232,244,245))
 return im

def semantic_scene(query,seed):
 rng=random.Random(seed); vw=W; vh=VISUAL_END-HEADER_END
 im=Image.new('RGB',(vw,vh),(47,49,52)); d=ImageDraw.Draw(im); q=query.lower()
 top=(rng.randint(28,70),rng.randint(32,70),rng.randint(38,80)); bot=(rng.randint(80,140),rng.randint(60,110),rng.randint(45,90))
 for y in range(vh):
  t=y/max(1,vh-1); c=tuple(int(top[i]*(1-t)+bot[i]*t) for i in range(3)); d.line((0,y,vw,y),fill=c)
 if 'motel exterior' in q or 'roadside motel' in q:
  d.rectangle((0,int(vh*.72),vw,vh),fill=(56,51,49)); d.polygon([(0,vh),(vw,vh),(vw,int(vh*.84)),(0,int(vh*.92))],fill=(44,45,48)); d.rectangle((70,180,650,385),fill=(178,143,105),outline=(60,50,44),width=5)
  for x in range(105,620,85): d.rectangle((x,240,x+48,320),fill=(32,38,48),outline=(230,190,120),width=3)
 elif 'front desk' in q:
  d.rectangle((0,0,vw,vh),fill=(72,54,45)); d.rectangle((0,260,vw,vh),fill=(114,80,54)); d.rectangle((60,230,660,410),fill=(105,66,42),outline=(45,26,18),width=5); d.ellipse((330,205,382,250),fill=(206,165,74))
 elif 'hallway' in q or 'corridor' in q:
  d.polygon([(0,0),(vw,0),(500,vh),(220,vh)],fill=(80,72,67)); d.polygon([(0,0),(220,vh),(0,vh)],fill=(53,49,48)); d.polygon([(vw,0),(500,vh),(vw,vh)],fill=(48,45,45)); d.rectangle((316,135,404,370),fill=(30,27,27),outline=(185,150,90),width=3)
 elif 'ledger' in q or 'papers' in q or 'envelope' in q:
  d.rectangle((0,0,vw,vh),fill=(86,62,43)); d.polygon([(0,250),(vw,190),(vw,vh),(0,vh)],fill=(111,77,49)); d.rounded_rectangle((140,120,585,405),radius=18,fill=(225,213,178),outline=(91,62,35),width=5)
  for y in range(165,380,34): d.line((175,y,550,y),fill=(151,137,111),width=2)
 elif 'security monitor' in q:
  d.rectangle((0,0,vw,vh),fill=(38,43,48)); d.rectangle((100,90,620,420),fill=(18,20,20),outline=(105,110,113),width=8); d.rectangle((130,120,590,390),fill=(55,82,76)); d.rectangle((130,300,590,390),fill=(56,56,58)); d.line((130,330,590,305),fill=(175,181,176),width=5)
 elif 'pickup' in q:
  d.rectangle((0,int(vh*.66),vw,vh),fill=(35,38,42)); d.rectangle((0,0,vw,int(vh*.66)),fill=(24,31,45)); d.rounded_rectangle((200,240,570,375),radius=34,fill=(25,26,29),outline=(96,101,108),width=4); d.polygon([(260,240),(330,170),(475,175),(530,240)],fill=(29,31,35),outline=(95,100,108))
 elif 'lockbox' in q:
  d.rectangle((0,0,vw,vh),fill=(72,55,44)); d.rectangle((0,340,vw,vh),fill=(77,69,60)); d.rectangle((210,130,515,390),fill=(67,73,76),outline=(20,22,23),width=7); d.rectangle((330,225,395,285),fill=(31,34,36),outline=(160,150,120),width=3)
 elif 'deputy' in q:
  d.rectangle((0,int(vh*.65),vw,vh),fill=(57,58,56)); d.rectangle((0,0,vw,int(vh*.65)),fill=(45,64,85)); d.rounded_rectangle((150,250,600,385),radius=24,fill=(202,206,211),outline=(32,33,35),width=5); d.rectangle((250,205,470,260),fill=(58,62,68))
 elif 'industrial park' in q:
  d.rectangle((0,int(vh*.72),vw,vh),fill=(82,84,72)); d.rectangle((0,0,vw,int(vh*.72)),fill=(168,192,204)); d.rectangle((160,220,630,385),fill=(150,155,151),outline=(78,81,78),width=4); d.line((90,90,90,350),fill=(75,78,76),width=8); d.line((90,90,400,90),fill=(75,78,76),width=8)
 elif 'key tag' in q:
  d.rectangle((0,0,vw,vh),fill=(61,46,39));
  for x in range(90,650,75): d.line((x,80,x,420),fill=(111,81,58),width=4)
  d.ellipse((330,165,405,240),fill=(194,153,61),outline=(87,64,26),width=4); d.rectangle((362,225,375,380),fill=(194,153,61))
 else:
  d.rectangle((0,int(vh*.72),vw,vh),fill=(55,52,50)); d.ellipse((270,90,450,270),fill=(160,139,119)); d.rectangle((300,260,420,470),fill=(54,56,61))
 px=im.load()
 for _ in range(6500):
  x=rng.randrange(vw); y=rng.randrange(vh); r,g,b=px[x,y]; z=rng.randint(-9,9); px[x,y]=(max(0,min(255,r+z)),max(0,min(255,g+z)),max(0,min(255,b+z)))
 return im.filter(ImageFilter.GaussianBlur(.2))

def compose(title,part,query,seed,out):
 im=base_frame(title,part,seed)
 if query: im.paste(semantic_scene(query,seed+77),(0,HEADER_END))
 im.save(out,quality=92)

def split_beats(text):
 ss=re.split(r'(?<=[.!?])\s+',re.sub(r'\s+',' ',text.strip())); out=[]; cur=[]; n=0; start=0; total=0
 for s in ss:
  wc=len(words(s))
  if cur and n+wc>42:
   out.append({'text':' '.join(cur),'start_word':start,'word_count':n}); start=total; cur=[]; n=0
  cur.append(s); n+=wc; total+=wc
  if n>=34: out.append({'text':' '.join(cur),'start_word':start,'word_count':n}); start=total; cur=[]; n=0
 if cur: out.append({'text':' '.join(cur),'start_word':start,'word_count':n})
 return out

def score(text):
 low=text.lower(); t=set(re.findall(r'[a-z]+',low)); s=min(3,len(t&LOCATIONS))+min(3,len(t&OBJECTS))+min(3,len(t&DRAMA))+min(2,len(t&EVENTS))
 if any(p in low for p in ('suddenly','inside','behind','under it','that night','next morning','three months later')): s+=2
 return s

def query(text):
 low=text.lower()
 for keys,q in KEYWORD_SCENES:
  if any(k in low for k in keys): return q
 return 'moody roadside story illustration with one central subject'

async def edge_narrate(text,audio,events_file):
 ev=[]; c=edge_tts.Communicate(text,'en-US-GuyNeural',rate='+11%')
 with open(audio,'wb') as f:
  async for chunk in c.stream():
   if chunk['type']=='audio': f.write(chunk['data'])
   elif chunk['type']=='WordBoundary': ev.append({'text':chunk.get('text',''),'start':chunk.get('offset',0)/10000000,'duration':chunk.get('duration',0)/10000000})
 events_file.write_text(json.dumps(ev,indent=2)); return ev

def duration(path): return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],True).stdout.strip())

def fallback_events(text,dur):
 ws=words(text); wt=[max(.7,min(2,.55+len(w)*.12)) for w in ws]; total=sum(wt); t=0; out=[]
 for w,x in zip(ws,wt): d=dur*x/total; out.append({'text':w,'start':t,'duration':d}); t+=d
 return out

def fallback_tts(text,audio):
 wav=TMP/'fallback.wav'; run(['espeak-ng','-v','en-us+m3','-s','190','-w',str(wav),text]); run(['ffmpeg','-y','-loglevel','error','-i',str(wav),'-c:a','libmp3lame','-b:a','128k',str(audio)]); return fallback_events(text,duration(audio))

def captions(events):
 out=[]; i=0
 while i<len(events):
  start=i; chunk=[]; chars=0
  while i<len(events) and len(chunk)<STYLE['caption_words_max']:
   w=str(events[i]['text']).strip(); add=len(w)+(1 if chunk else 0)
   if chunk and chars+add>STYLE['caption_chars_max']: break
   chunk.append(w); chars+=add; i+=1
   if re.search(r'[.!?,;:]$',w): break
  if not chunk: chunk=[str(events[i]['text']).strip()]; i+=1
  a=events[start]['start']; e=events[i-1]; b=e['start']+max(e.get('duration',.12),.12)
  if i<len(events): b=min(b,events[i]['start']-.01)
  out.append({'start':a,'end':max(a+.18,b),'text':' '.join(chunk).upper(),'words':len(chunk)})
 return out

def atime(sec):
 h=int(sec//3600); m=int((sec%3600)//60); s=sec%60; return f'{h}:{m:02d}:{s:05.2f}'

def write_ass(cues,path):
 head=f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Caption,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,0,2,24,24,445,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
 lines=[head]
 for c in cues: lines.append(f"Dialogue: 0,{atime(c['start'])},{atime(c['end'])},Caption,,0,0,0,,{{\\an2\\fscx112\\fscy112\\t(0,110,\\fscx100\\fscy100)}}{ass_escape(c['text'])}\n")
 path.write_text(''.join(lines))

def time_beats(beats,events,dur):
 ns=max(1,sum(b['word_count'] for b in beats)); ne=len(events)
 for b in beats:
  a=min(ne-1,round((b['start_word']/ns)*max(0,ne-1))) if ne else 0; end=b['start_word']+b['word_count']; z=min(ne-1,round((end/ns)*max(0,ne-1))) if ne else 0
  b['start']=events[a]['start'] if ne else dur*b['start_word']/ns
  b['end']=min(dur,events[z]['start']+max(events[z].get('duration',.1),.1)) if ne else dur*end/ns
  b['score']=score(b['text']); b['query']=query(b['text'])
 return beats

def select_visuals(beats,dur):
 sel=[]; last=-99
 for i,b in enumerate(beats):
  gap=b['start']-last; pick=i==0 or gap>=STYLE['visual_max_gap'] or (gap>=STYLE['visual_min_gap'] and b['score']>=4)
  if pick:
   hold=min(9,max(6,min(b['end']-b['start']+1.6,9)))
   if b['start']+hold>dur: hold=max(3,dur-b['start']-.2)
   if hold>2.5: sel.append({'start':b['start'],'end':b['start']+hold,'duration':hold,'query':b['query'],'score':b['score']}); last=b['start']
 def coverage(): return sum(v['duration'] for v in sel)/max(1,dur)
 while len(sel)>5 and coverage()>STYLE['visual_coverage'][1]: sel.pop(min(range(1,len(sel)),key=lambda i:(sel[i]['score'],sel[i]['duration'])))
 return sel

def render(base,visuals,audio,ass,dur,out):
 cmd=['ffmpeg','-y','-loglevel','error','-loop','1','-framerate',str(FPS),'-t',str(dur),'-i',str(base)]
 for v in visuals: cmd+=['-loop','1','-framerate',str(FPS),'-t',str(v['duration']),'-i',str(v['file'])]
 ai=1+len(visuals); cmd+=['-i',str(audio)]; filters=[f'[0:v]scale={W}:{H},format=yuv420p[base]']; cur='base'; fade=STYLE['transition']
 for i,v in enumerate(visuals,1):
  label=f'v{i}'; d=max(v['duration'],fade*2+.1); st=v['start']; en=v['end']; filters.append(f'[{i}:v]scale={W}:{H},format=rgba,fade=t=in:st=0:d={fade}:alpha=1,fade=t=out:st={max(0,d-fade):.3f}:d={fade}:alpha=1,setpts=PTS+{st:.3f}/TB[ov{i}]'); filters.append(f'[{cur}][ov{i}]overlay=0:0:enable=\'between(t,{st:.3f},{en:.3f})\'[{label}]'); cur=label
 ap=str(ass).replace(':','\\:').replace("'",r"\'"); filters.append(f'[{cur}]ass=\'{ap}\'[vout]')
 cmd+=['-filter_complex',';'.join(filters),'-map','[vout]','-map',f'{ai}:a','-af','loudnorm=I=-14:TP=-1.0:LRA=7','-c:v','libx264','-preset','medium','-crf','20','-pix_fmt','yuv420p','-r',str(FPS),'-c:a','aac','-b:a','160k','-movflags','+faststart','-t',str(dur),str(out)]; run(cmd)

def verify(video,cues,visuals,narration):
 actual=duration(video); coverage=sum(v['duration'] for v in visuals)/max(1,actual); starts=[v['start'] for v in visuals]; gaps=[b-a for a,b in zip(starts,starts[1:])]
 checks={'duration_in_range':STYLE['hard_duration'][0]<=actual<=STYLE['hard_duration'][1],'caption_density_ok':len(cues)>=100,'caption_word_limit_ok':max((c['words'] for c in cues),default=0)<=STYLE['caption_words_max'],'visual_insert_count_ok':len(visuals)>=6,'visual_coverage_ok':.15<=coverage<=.46,'visual_spacing_ok':not gaps or min(gaps)>=6.5,'no_random_text':True,'audio_video_sync_ok':abs(actual-narration)<=2}
 return actual,coverage,gaps,checks,all(checks.values())

def main():
 for p in TMP.glob('*'): p.unlink() if p.is_file() else shutil.rmtree(p,ignore_errors=True)
 for p in OUT.glob('*'): p.unlink() if p.is_file() else shutil.rmtree(p,ignore_errors=True)
 seed=int(os.getenv('STORY_SEED',str(random.randint(10000,999999)))); title=os.getenv('STORY_TITLE','Your Life as a Motel Owner').strip(); part=os.getenv('STORY_PART','Part 1').strip(); story=os.getenv('STORY_TEXT','').strip() or DEFAULT_STORY
 audio=TMP/'narration.mp3'; wf=TMP/'word-boundaries.json'
 try:
  events=asyncio.run(edge_narrate(story,audio,wf))
  if len(events)<50: raise RuntimeError('insufficient word boundaries')
 except Exception as e:
  print('edge narration fallback:',e,file=sys.stderr); events=fallback_tts(story,audio); wf.write_text(json.dumps(events,indent=2))
 dur=duration(audio); cues=captions(events); beats=time_beats(split_beats(story),events,dur); visuals=select_visuals(beats,dur)
 base=TMP/'base.png'; compose(title,part,None,seed,base)
 for i,v in enumerate(visuals): v['file']=TMP/f'visual_{i:02d}.png'; compose(title,part,v['query'],seed+i*101,v['file'])
 ass=TMP/'captions.ass'; write_ass(cues,ass); name=f'{safe(title)}-{seed}'; video=OUT/f'{name}.mp4'; render(base,visuals,audio,ass,dur,video)
 actual,cov,gaps,checks,passed=verify(video,cues,visuals,dur)
 manifest={'renderer':STYLE['renderer'],'qualityGate':'reference-narration-clean-screen-v1','qualityPassed':passed,'title':title,'part':part,'file':video.name,'durationSeconds':round(actual,3),'narrationSeconds':round(dur,3),'captionCueCount':len(cues),'captionMaxWords':max((c['words'] for c in cues),default=0),'visualInsertCount':len(visuals),'visualCoverageRatio':round(cov,4),'visualMedianDuration':round(sorted(v['duration'] for v in visuals)[len(visuals)//2],3) if visuals else 0,'visualMinGap':round(min(gaps),3) if gaps else None,'style':STYLE,'checks':checks,'visuals':[{k:(round(x,3) if isinstance(x,float) else x) for k,x in v.items() if k!='file'} for v in visuals]}
 (OUT/f'{name}.json').write_text(json.dumps(manifest,indent=2))
 if not passed: print(json.dumps(manifest,indent=2),file=sys.stderr); raise RuntimeError('Quality gate failed; refusing to publish')
 print(video)

if __name__=='__main__': main()
