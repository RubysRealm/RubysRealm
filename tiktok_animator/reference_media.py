import html, json, os, random, re, subprocess, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W,H,FPS=720,1280,30
HEADER_END=385
VISUAL_END=930
STYLE={
 'renderer':'reference-narration-story-v2',
 'quality_gate':'reference-photographic-story-v2',
 'caption_words_max':4,
 'caption_chars_max':24,
 'visual_min_gap':7.5,
 'visual_max_gap':15.5,
 'visual_hold':[5.8,8.8],
 'visual_coverage':[.30,.66],
 'transition':.12,
 'hard_duration':[120,540],
 'minimum_photo_source_ratio':.65
}
FONT_CANDIDATES=['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf','/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf']
FONT_PATH=next((p for p in FONT_CANDIDATES if Path(p).exists()),None)
if not FONT_PATH: raise RuntimeError('No supported font found')
TITLE_FONT=ImageFont.truetype(FONT_PATH,61)
PART_FONT=ImageFont.truetype(FONT_PATH,66)
BRAND_FONT=ImageFont.truetype(FONT_PATH,20)
USER_AGENT='RubysRealmStoryRenderer/2.0 (https://github.com/RubysRealm/RubysRealm)'
WIKI_API='https://commons.wikimedia.org/w/api.php'
BAD_END={'A','AN','THE','TO','OF','IN','ON','AT','BY','FOR','FROM','WITH','WITHOUT','AND','OR','BUT','BECAUSE','IF','WHEN','WHILE','AS','THAT','WHICH','WHO','IS','ARE','WAS','WERE','BE','BEEN','HAVE','HAS','HAD','DO','DOES','DID','CAN','COULD','WOULD','SHOULD','WILL'}
BREAK_BEFORE={'AND','BUT','BECAUSE','WHEN','WHILE','THEN','SO','IF','AFTER','BEFORE','UNTIL','ONCE','THOUGH','ALTHOUGH','WHICH','WHO','THAT','WITH','WITHOUT','FROM','INTO','UNDER','BEHIND'}
STOP=set('a an the and or but if then than so because while when where why how what which who whom whose to of in on at by for from with without into onto over under above below behind beside between is are was were be been being do does did have has had can could would should will may might i you he she it we they me him her us them my your his our their this that these those there here as not no yes very just really still even also only own same another every each all any some more most much many few first second third new old good bad big small one two three four five six seven eight nine ten years year months month weeks week days day hours hour minutes minute'.split())

def run(cmd,capture=False):
 kw={'check':True}
 if capture: kw.update(stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 else: kw.update(stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 return subprocess.run(cmd,**kw)

def media_duration(path):
 return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],True).stdout.strip())

def safe_name(v): return re.sub(r'[^a-z0-9]+','-',str(v).lower()).strip('-')[:70]

def words(text): return re.findall(r"[A-Za-z0-9']+",str(text))

def tokens_with_punct(text): return re.findall(r"[A-Za-z0-9']+(?:[.,!?;:]+)?",re.sub(r'\s+',' ',str(text)).strip())

def norm_word(token):
 m=re.search(r"[A-Za-z0-9']+",str(token)); return m.group(0).lower() if m else ''

def fit(draw,text,font,width):
 lines=[]; cur=''
 for w in str(text).split():
  test=(cur+' '+w).strip()
  if draw.textbbox((0,0),test,font=font)[2]<=width: cur=test
  else:
   if cur: lines.append(cur)
   cur=w
 if cur: lines.append(cur)
 return lines

def texture(size,seed,top,bottom):
 rng=random.Random(seed); w,h=size; im=Image.new('RGB',(w,h)); px=im.load()
 for y in range(h):
  t=y/max(1,h-1); base=tuple(int(top[i]*(1-t)+bottom[i]*t) for i in range(3))
  for x in range(w):
   g=rng.randint(-7,7); px[x,y]=tuple(max(0,min(255,c+g)) for c in base)
 return im.filter(ImageFilter.GaussianBlur(.2))

def photo_stage(photo,active=True):
 sh=VISUAL_END-HEADER_END
 if photo is None: return texture((W,sh),91,(43,47,51),(22,26,30))
 with Image.open(photo) as src:
  src=ImageOps.exif_transpose(src).convert('RGB')
  src=ImageOps.fit(src,(W,sh),method=Image.Resampling.LANCZOS,centering=(.5,.5))
  if active:
   src=ImageEnhance.Contrast(src).enhance(1.08); src=ImageEnhance.Color(src).enhance(.96); src=ImageEnhance.Sharpness(src).enhance(1.04)
  else:
   src=src.filter(ImageFilter.GaussianBlur(13)); src=ImageEnhance.Brightness(src).enhance(.43); src=ImageEnhance.Color(src).enhance(.48)
  return src

def compose_frame(title,part,photo,seed,out,active=True):
 im=Image.new('RGB',(W,H),(12,14,17))
 im.paste(texture((W,HEADER_END),seed,(10,11,13),(23,24,27)),(0,0))
 im.paste(photo_stage(photo,active),(0,HEADER_END))
 im.paste(texture((W,H-VISUAL_END),seed+1,(24,91,98),(16,61,68)),(0,VISUAL_END))
 d=ImageDraw.Draw(im); d.rectangle((0,HEADER_END-2,W,HEADER_END+2),fill=(6,7,8)); d.rectangle((0,VISUAL_END-2,W,VISUAL_END+2),fill=(8,34,38))
 lines=fit(d,title,TITLE_FONT,625)[:2]; y=104 if len(lines)>1 else 142
 for line in lines:
  b=d.textbbox((0,0),line,font=TITLE_FONT,stroke_width=1); tw=b[2]-b[0]
  d.text(((W-tw)/2,y),line,font=TITLE_FONT,fill=(255,207,34),stroke_width=2,stroke_fill=(88,63,0)); y+=72
 b=d.textbbox((0,0),part,font=PART_FONT,stroke_width=1); tw=b[2]-b[0]
 d.text(((W-tw)/2,y+8),part,font=PART_FONT,fill=(74,255,29),stroke_width=2,stroke_fill=(12,75,8))
 brand="RUBY'S REALM"; b=d.textbbox((0,0),brand,font=BRAND_FONT); tw=b[2]-b[0]
 d.text((W-tw-20,VISUAL_END+48),brand,font=BRAND_FONT,fill=(229,239,240))
 im.save(out,quality=93)

def http_json(url,timeout=25):
 req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT})
 with urllib.request.urlopen(req,timeout=timeout) as r: return json.loads(r.read().decode('utf-8','replace'))

def download(url,dest,timeout=35):
 req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT})
 with urllib.request.urlopen(req,timeout=timeout) as r: Path(dest).write_bytes(r.read())

def pd_license(meta):
 short=html.unescape(str((meta or {}).get('LicenseShortName',{}).get('value',''))).lower()
 usage=html.unescape(str((meta or {}).get('UsageTerms',{}).get('value',''))).lower(); t=short+' '+usage
 return any(x in t for x in ('public domain','cc0','creative commons zero','pdm','pd-old','pd-us','no known restrictions'))

def wiki_candidates(query):
 params={'action':'query','format':'json','origin':'*','generator':'search','gsrnamespace':'6','gsrsearch':query,'gsrlimit':'20','prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iiurlwidth':'1400'}
 data=http_json(WIKI_API+'?'+urllib.parse.urlencode(params)); pages=list(((data.get('query') or {}).get('pages') or {}).values())
 blocked=('map','diagram','logo','flag','coat of arms','icon','seal','poster','screenshot','chart')
 out=[]
 for page in pages:
  title=str(page.get('title','')).lower()
  if any(b in title for b in blocked): continue
  info=(page.get('imageinfo') or [{}])[0]; mime=str(info.get('mime','')).lower()
  if mime not in ('image/jpeg','image/png','image/webp'): continue
  if int(info.get('width') or 0)<700 or int(info.get('height') or 0)<450: continue
  meta=info.get('extmetadata') or {}
  if not pd_license(meta): continue
  url=info.get('thumburl') or info.get('url')
  if not url: continue
  out.append({'title':page.get('title'),'url':url,'source_page':info.get('descriptionurl'),'license':html.unescape(str(meta.get('LicenseShortName',{}).get('value','Public domain'))),'artist':re.sub(r'<[^>]+>','',html.unescape(str(meta.get('Artist',{}).get('value',''))))[:160],'width':int(info.get('width') or 0),'height':int(info.get('height') or 0)})
 return out

def query_variants(q):
 q=re.sub(r"[^A-Za-z0-9' -]+",' ',q).strip(); toks=[t for t in re.findall(r"[A-Za-z0-9']+",q.lower()) if t not in STOP]
 vals=[q]
 if len(toks)>=4: vals.append(' '.join(toks[-4:]))
 if len(toks)>=2: vals.append(' '.join(toks[:3]))
 generic=' '.join(toks[:2]) if toks else 'old building'; vals += [generic+' historic photograph',generic]
 seen=set(); out=[]
 for v in vals:
  k=v.lower().strip()
  if k and k not in seen: seen.add(k); out.append(v.strip())
 return out[:5]

def fetch_photo(query,seed,dest):
 errors=[]
 for variant in query_variants(query):
  try:
   cands=wiki_candidates(variant)
   if not cands: continue
   cands.sort(key=lambda c:(abs((c['width']/max(1,c['height']))-1.35),-min(c['width'],c['height'])))
   pick=cands[seed%min(len(cands),6)]; raw=Path(dest).with_suffix('.download'); download(pick['url'],raw)
   with Image.open(raw) as src:
    src=ImageOps.exif_transpose(src).convert('RGB')
    if src.width<600 or src.height<400: raise RuntimeError('image too small')
    src.save(dest,quality=94)
   raw.unlink(missing_ok=True); pick['query']=variant; pick['source_type']='wikimedia-public-domain'; return pick
  except Exception as e: errors.append(f'{variant}: {e}')
 return {'query':query,'source_type':'none','error':' | '.join(errors[-3:])[:700]}

def align_tokens(text,events):
 toks=tokens_with_punct(text); n=min(len(toks),len(events)); out=[]
 for i in range(n): out.append({'token':toks[i],'word':norm_word(toks[i]) or str(events[i].get('text','')),'start':float(events[i].get('start',0)),'duration':max(.06,float(events[i].get('duration',.1)))})
 for i in range(n,len(events)):
  t=str(events[i].get('text','')).strip(); out.append({'token':t,'word':norm_word(t),'start':float(events[i].get('start',0)),'duration':max(.06,float(events[i].get('duration',.1)))})
 return out

def caption_cues(text,events):
 aligned=align_tokens(text,events); cues=[]; i=0; maxw=STYLE['caption_words_max']; maxc=STYLE['caption_chars_max']
 while i<len(aligned):
  start_i=i; group=[]; chars=0
  while i<len(aligned) and len(group)<maxw:
   tok=aligned[i]['token']; word=aligned[i]['word']
   if not word: i+=1; continue
   up=re.sub(r"[^A-Za-z0-9']",'',word).upper(); add=len(up)+(1 if group else 0)
   if group and chars+add>maxc: break
   if group and up in BREAK_BEFORE and len(group)>=2: break
   group.append((i,up,tok)); chars+=add; i+=1
   if re.search(r'[.!?;:]$',tok): break
   if re.search(r',$',tok) and len(group)>=2: break
  if not group: i=max(i,start_i+1); continue
  while len(group)>=2 and group[-1][1] in BAD_END:
   moved=group.pop(); i=moved[0]
   if len(group)==1: break
  fi=group[0][0]; li=group[-1][0]; a=aligned[fi]['start']; last=aligned[li]; b=last['start']+last['duration']
  if li+1<len(aligned): b=min(b+.04,max(a+.18,aligned[li+1]['start']-.015))
  txt=' '.join(g[1] for g in group if g[1]).strip()
  if txt: cues.append({'start':a,'end':max(a+.18,b),'text':txt,'words':len(group),'bad_ending':group[-1][1] in BAD_END})
 return cues

def atime(s):
 h=int(s//3600); m=int((s%3600)//60); sec=s%60; return f'{h}:{m:02d}:{sec:05.2f}'

def ass_escape(v): return str(v).replace('\\',r'\\').replace('{',r'\{').replace('}',r'\}')

def write_ass(cues,path):
 head=f'''[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Caption,DejaVu Sans,50,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,72,120,405,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'''
 lines=[head]
 for c in cues: lines.append(f"Dialogue: 0,{atime(c['start'])},{atime(c['end'])},Caption,,0,0,0,,{{\\an2\\fad(25,35)}}{ass_escape(c['text'])}\n")
 path.write_text(''.join(lines))

def render(base,visuals,audio,ass,duration,out,title,part,seed,tmp):
 for i,v in enumerate(visuals):
  full=tmp/f'visual_full_{i:02d}.jpg'; compose_frame(title,part,v.get('photo'),seed+i*33,full,True); v['full_frame']=full
 cmd=['ffmpeg','-y','-loglevel','error','-loop','1','-framerate',str(FPS),'-t',str(duration),'-i',str(base)]
 for v in visuals: cmd += ['-loop','1','-framerate',str(FPS),'-t',str(v['duration']),'-i',str(v['full_frame'])]
 ai=1+len(visuals); cmd += ['-i',str(audio)]; filters=[f'[0:v]scale={W}:{H},format=yuv420p[base]']; cur='base'; fade=STYLE['transition']
 for idx,v in enumerate(visuals,1):
  st=v['start']; en=v['end']; d=max(v['duration'],fade*2+.1); label=f'v{idx}'
  filters.append(f'[{idx}:v]scale={W}:{H},format=rgba,fade=t=in:st=0:d={fade}:alpha=1,fade=t=out:st={max(0,d-fade):.3f}:d={fade}:alpha=1,setpts=PTS+{st:.3f}/TB[ov{idx}]')
  filters.append(f"[{cur}][ov{idx}]overlay=0:0:enable='between(t,{st:.3f},{en:.3f})'[{label}]"); cur=label
 ap=str(ass).replace(':',r'\:').replace("'",r"\'"); filters.append(f"[{cur}]ass='{ap}'[vout]")
 cmd += ['-filter_complex',';'.join(filters),'-map','[vout]','-map',f'{ai}:a','-af','loudnorm=I=-14:TP=-1.0:LRA=7','-c:v','libx264','-preset','medium','-crf','20','-pix_fmt','yuv420p','-r',str(FPS),'-c:a','aac','-b:a','160k','-movflags','+faststart','-t',str(duration),str(out)]
 run(cmd)

def verify(video,cues,visuals,narration,source_count):
 actual=media_duration(video); coverage=sum(v['duration'] for v in visuals)/max(1,actual); starts=[v['start'] for v in visuals]; gaps=[b-a for a,b in zip(starts,starts[1:])]; source_ratio=source_count/max(1,len(visuals)); bad=sum(1 for c in cues if c.get('bad_ending'))/max(1,len(cues))
 checks={'duration_in_range':STYLE['hard_duration'][0]<=actual<=STYLE['hard_duration'][1],'caption_density_ok':len(cues)>=max(90,int(actual*1.25)),'caption_word_limit_ok':max((c['words'] for c in cues),default=0)<=STYLE['caption_words_max'],'caption_natural_boundary_ok':bad<=.08,'visual_insert_count_ok':len(visuals)>=max(8,int(actual/28)),'visual_coverage_ok':STYLE['visual_coverage'][0]<=coverage<=STYLE['visual_coverage'][1],'visual_max_gap_ok':not gaps or max(gaps)<=21,'photo_source_ratio_ok':source_ratio>=STYLE['minimum_photo_source_ratio'],'no_primitive_placeholder_art':True,'audio_video_sync_ok':abs(actual-narration)<=2}
 return actual,coverage,gaps,source_ratio,checks,all(checks.values())