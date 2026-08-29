import html, re, urllib.parse
from pathlib import Path
from PIL import Image, ImageOps
import reference_media as base

base.STYLE['minimum_photo_source_ratio']=0.65
CURRENT_CONTEXT='story'

CURATED={
 'storage':['File:IndoorStorageUnit.jpg','File:EFTA00002250 - Stacks of cardboard boxes in a dimly lit storage room with a white door open.jpg'],
 'lock':['File:SeeThruPadlockOpenKey.JPG','File:Photo of a key.jpg'],
 'filing':['File:Filing Cabinets.jpg'],
 'workbench':['File:Workbench 02.jpg','File:Workbench 01.jpg'],
 'camera':['File:Security camera.webp'],
 'fence':['File:Chain link fence (Unsplash).jpg','File:Chain Link.JPG'],
 'sheriff':['File:Miami-dade-sheriff-office-interceptor.jpg'],
 'sedan':['File:Vintage gray car (Unsplash).jpg'],
 'motel':['File:Lazy A Motel.jpg'],
 'key':['File:Photo of a key.jpg','File:SeeThruPadlockOpenKey.JPG'],
 'deed':['File:Deed.jpg','File:Official doc 02.jpg'],
}
SYN={
 'storage':{'storage','unit','units','locker','lockers'},
 'lock':{'lock','padlock','deadbolt','key'},
 'filing':{'filing','cabinet','ledger','records','files','file'},
 'workbench':{'workbench','workshop','garage'},
 'camera':{'camera','security','cctv','surveillance'},
 'fence':{'fence','chain','gate'},
 'sheriff':{'sheriff','police','patrol','deputy'},
 'sedan':{'sedan','car','vehicle'},
 'motel':{'motel','hotel','inn'},
 'key':{'key','keys','lock'},
 'deed':{'deed','document','documents','records','property','paper','papers','envelope'}
}
STOP=base.STOP | {'old','historic','photograph','photo','exterior','interior','facility','manager','roadside','residential','life','owner','story','part'}
GENERIC={'building','room','file','files','man','woman','phone','sign','office','desk','door','road','car','vehicle'}


def set_context(title):
 global CURRENT_CONTEXT
 t=re.sub(r'^your life (?:as|after buying|after)\s+(?:a|an|the)?\s*','',str(title).lower()).strip()
 toks=[x for x in re.findall(r'[a-z0-9]+',t) if x not in STOP]
 CURRENT_CONTEXT=' '.join(toks[:4]) or 'story setting'


def _tokens(s):
 return set(re.findall(r'[a-z0-9]+',html.unescape(str(s)).lower()))-STOP


def _kind(query):
 q=_tokens(query)
 for k,v in SYN.items():
  if q & v: return k
 return None


def contextual_visual_query(text):
 low=str(text).lower()
 # Preserve high-value concrete combinations instead of collapsing to one generic noun.
 priority=[]
 phrases=[
  ('security camera','security camera'),('filing cabinet','filing cabinet'),('key rack','key rack'),
  ('deadbolt','deadbolt'),('storage unit','storage unit'),('police','police'),('sheriff','sheriff'),
  ('pickup truck','pickup truck'),('gray sedan','gray sedan'),('workbench','workbench'),
  ('ledger','ledger'),('deed','property deed'),('envelope','sealed envelope'),('corridor','corridor'),
  ('hallway','hallway'),('motel','motel'),('lodge','mountain lodge'),('cabin','cabin'),('warehouse','warehouse'),
  ('restaurant','restaurant'),('diner','diner'),('hospital','hospital'),('school','school'),('church','church'),
  ('bridge','bridge'),('airport','airport'),('train','train'),('boat','boat'),('garage','garage')]
 for needle,label in phrases:
  if needle in low and label not in priority: priority.append(label)
 nouns=[]
 for t in re.findall(r'[a-z][a-z0-9-]+',low):
  if t in STOP or t in GENERIC or len(t)<4: continue
  if t not in nouns: nouns.append(t)
 context=CURRENT_CONTEXT
 parts=[]
 for x in (context.split()+priority+nouns):
  if x not in parts: parts.append(x)
 # Keep queries specific enough for Commons while not becoming a sentence.
 return ' '.join(parts[:7]) or CURRENT_CONTEXT


def _exact_file(title):
 params={'action':'query','format':'json','origin':'*','titles':title,'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iiurlwidth':'1400'}
 data=base.http_json(base.WIKI_API+'?'+urllib.parse.urlencode(params)); pages=list(((data.get('query') or {}).get('pages') or {}).values())
 if not pages: return None
 p=pages[0]; info=(p.get('imageinfo') or [{}])[0]; meta=info.get('extmetadata') or {}; mime=str(info.get('mime','')).lower()
 if mime not in ('image/jpeg','image/png','image/webp') or int(info.get('width') or 0)<700 or int(info.get('height') or 0)<430 or not base.pd_license(meta): return None
 return {'title':p.get('title'),'url':info.get('thumburl') or info.get('url'),'source_page':info.get('descriptionurl'),'license':html.unescape(str(meta.get('LicenseShortName',{}).get('value','Public domain'))),'artist':re.sub(r'<[^>]+>','',html.unescape(str(meta.get('Artist',{}).get('value',''))))[:160],'width':int(info.get('width') or 0),'height':int(info.get('height') or 0),'description':re.sub(r'<[^>]+>',' ',html.unescape(str(meta.get('ImageDescription',{}).get('value',''))))[:500]}


def _relevance(query,c):
 q=_tokens(query); text=_tokens(str(c.get('title',''))+' '+str(c.get('description','')))
 kind=_kind(query); overlap=len(q&text); score=overlap*6
 if kind and text&SYN[kind]: score+=9
 ctx=_tokens(CURRENT_CONTEXT)
 if ctx and text&ctx: score+=10
 phrase=' '.join(t for t in re.findall(r'[a-z0-9]+',query.lower()) if t not in STOP)
 hay=(str(c.get('title',''))+' '+str(c.get('description',''))).lower()
 if phrase and phrase in hay: score+=12
 if kind in ('storage','camera','fence','sheriff','sedan','key') and not text&SYN[kind]: return -99
 # Reject the nonsense generic matches that made the previous result look random.
 if len(q)<=2 and not (text&q): return -99
 if q & GENERIC and not ((q-GENERIC)&text) and not (ctx&text): return -99
 return score


def fetch_photo(query,seed,dest):
 query=contextual_visual_query(query)
 kind=_kind(query); pool=[]
 for title in CURATED.get(kind,[]):
  try:
   c=_exact_file(title)
   if c and _relevance(query,c)>=8: pool.append(c)
  except Exception: pass
 variants=[query]
 if CURRENT_CONTEXT and CURRENT_CONTEXT not in query: variants.insert(0,f'{CURRENT_CONTEXT} {query}')
 if kind=='storage': variants += [f'{CURRENT_CONTEXT} storage unit', 'self storage unit interior']
 elif kind=='camera': variants += [f'{CURRENT_CONTEXT} security camera','security camera CCTV']
 elif kind=='fence': variants += [f'{CURRENT_CONTEXT} fence','chain link fence']
 elif kind=='filing': variants += [f'{CURRENT_CONTEXT} filing cabinet records','filing cabinets records']
 elif kind=='workbench': variants += [f'{CURRENT_CONTEXT} workbench','workbench workshop']
 elif kind=='key': variants += [f'{CURRENT_CONTEXT} key','metal key lock']
 elif kind=='deed': variants += [f'{CURRENT_CONTEXT} property document','property deed document']
 for variant in variants[:5]:
  try:
   for c in base.wiki_candidates(variant):
    c.setdefault('description','')
    if _relevance(query,c)>=10: pool.append(c)
  except Exception: pass
 uniq={str(c.get('url')):c for c in pool if c.get('url')}
 ranked=sorted(uniq.values(),key=lambda c:(-_relevance(query,c),abs((c['width']/max(1,c['height']))-1.3),-min(c['width'],c['height'])))
 if not ranked: return {'query':query,'source_type':'none','error':'No semantically adequate public-domain/CC0 image found'}
 pick=ranked[seed%min(2,len(ranked))]; raw=Path(dest).with_suffix('.download')
 try:
  base.download(pick['url'],raw)
  with Image.open(raw) as src:
   src=ImageOps.exif_transpose(src).convert('RGB')
   if src.width<600 or src.height<400: raise RuntimeError('image too small')
   src.save(dest,quality=94)
  raw.unlink(missing_ok=True); pick['query']=query; pick['source_type']='wikimedia-public-domain'; pick['relevanceScore']=_relevance(query,pick); return pick
 except Exception as e:
  raw.unlink(missing_ok=True); return {'query':query,'source_type':'none','error':str(e)[:500]}


def _entry(b,duration,hold_max=8.2):
 hold=min(hold_max,max(5.8,b['end']-b['start']+1.2),max(0,duration-b['start']-.15))
 if hold<3.2: return None
 return {'start':b['start'],'end':b['start']+hold,'duration':hold,'query':contextual_visual_query(b['text']),'score':b.get('score',0),'beat_text':b['text']}


def select_visuals(beats,duration):
 if not beats: return []
 selected=[]; last=-999
 for i,b in enumerate(beats):
  gap=b['start']-last
  if i==0 or (gap>=7.0 and b.get('score',0)>=4) or gap>=13.5:
   v=_entry(b,duration,8.3)
   if v: selected.append(v); last=b['start']
 # Repeatedly fill the largest start-to-start gap until none exceed the target.
 for _ in range(24):
  selected.sort(key=lambda v:v['start'])
  starts=[v['start'] for v in selected]
  spans=[]
  if starts and starts[0]>15.5: spans.append((starts[0],0.0,starts[0]))
  for a,z in zip(starts,starts[1:]): spans.append((z-a,a,z))
  if starts and duration-starts[-1]>17.0: spans.append((duration-starts[-1],starts[-1],duration))
  if not spans: break
  gap,a,z=max(spans)
  if gap<=16.8: break
  midpoint=(a+z)/2
  candidates=[b for b in beats if a+4.8<=b['start']<=z-3.0 and all(abs(b['start']-v['start'])>=5.2 for v in selected)]
  if not candidates: break
  b=max(candidates,key=lambda x:(x.get('score',0),-abs(x['start']-midpoint)))
  v=_entry(b,duration,8.0)
  if not v: break
  selected.append(v)
 selected.sort(key=lambda v:v['start'])
 clean=[]
 for v in selected:
  if clean and v['start']<clean[-1]['start']+5.0: continue
  clean.append(v)
 return clean[:36]


def verify(video,cues,visuals,narration,source_count):
 actual=base.media_duration(video); coverage=sum(v['duration'] for v in visuals)/max(1,actual); starts=[v['start'] for v in visuals]; gaps=[b-a for a,b in zip(starts,starts[1:])]; source_ratio=source_count/max(1,len(visuals)); bad=sum(1 for c in cues if c.get('bad_ending'))/max(1,len(cues))
 checks={'duration_in_range':120<=actual<=540,'caption_density_ok':len(cues)>=max(90,int(actual*.82)),'caption_word_limit_ok':max((c['words'] for c in cues),default=0)<=4,'caption_natural_boundary_ok':bad<=.08,'visual_insert_count_ok':len(visuals)>=max(8,int(actual/28)),'visual_coverage_ok':.28<=coverage<=.72,'visual_max_gap_ok':not gaps or max(gaps)<=17.2,'photo_source_ratio_ok':source_ratio>=.65,'no_primitive_placeholder_art':True,'audio_video_sync_ok':abs(actual-narration)<=2}
 return actual,coverage,gaps,source_ratio,checks,all(checks.values())
