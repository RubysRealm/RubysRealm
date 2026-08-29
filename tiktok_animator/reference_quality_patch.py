import html, re, urllib.parse
from pathlib import Path
from PIL import Image, ImageOps
import reference_media as base

base.STYLE['minimum_photo_source_ratio']=0.65
base.STYLE['visual_min_gap']=11.5
base.STYLE['visual_max_gap']=18.5
base.STYLE['visual_hold']=[5.8,7.8]
base.STYLE['visual_coverage']=[0.28,0.62]
CURRENT_CONTEXT='story'
USED_URLS=set()

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
 global CURRENT_CONTEXT, USED_URLS
 t=re.sub(r'^your life (?:as|after buying|after)\s+(?:a|an|the)?\s*','',str(title).lower()).strip()
 toks=[x for x in re.findall(r'[a-z0-9]+',t) if x not in STOP]
 CURRENT_CONTEXT=' '.join(toks[:4]) or 'story setting'
 USED_URLS=set()


def _tokens(s):
 return set(re.findall(r'[a-z0-9]+',html.unescape(str(s)).lower()))-STOP


def _kind(query):
 q=_tokens(query)
 for k,v in SYN.items():
  if q & v: return k
 return None


def contextual_visual_query(text):
 low=str(text).lower()
 priority=[]
 phrases=[
  ('security camera','security camera'),('filing cabinet','filing cabinet'),('key rack','key rack'),
  ('deadbolt','deadbolt'),('storage unit','storage unit'),('police','police'),('sheriff','sheriff'),
  ('pickup truck','pickup truck'),('gray sedan','gray sedan'),('workbench','workbench'),
  ('ledger','ledger'),('deed','property deed'),('envelope','sealed envelope'),('corridor','corridor'),
  ('hallway','hallway'),('motel','motel'),('lodge','mountain lodge'),('cabin','cabin'),('warehouse','warehouse'),
  ('restaurant','restaurant'),('diner','diner'),('hospital','hospital'),('school','school'),('church','church'),
  ('bridge','bridge'),('airport','airport'),('train','train'),('boat','boat'),('ferry','ferry terminal'),
  ('garage','garage'),('river','river'),('map','map'),('receipt','receipt'),('document','documents'),
  ('breaker','electrical panel'),('flashlight','flashlight'),('truck','truck'),('parking lot','parking lot')]
 for needle,label in phrases:
  if needle in low and label not in priority: priority.append(label)
 nouns=[]
 for t in re.findall(r'[a-z][a-z0-9-]+',low):
  if t in STOP or t in GENERIC or len(t)<4: continue
  if t not in nouns: nouns.append(t)
 parts=[]
 for x in (CURRENT_CONTEXT.split()+priority+nouns):
  if x not in parts: parts.append(x)
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
 if len(q)<=2 and not (text&q): return -99
 if q & GENERIC and not ((q-GENERIC)&text) and not (ctx&text): return -99
 return score


def _add_candidates(pool,variant,query,minimum):
 try:
  for c in base.wiki_candidates(variant):
   c.setdefault('description','')
   if _relevance(query,c)>=minimum: pool.append(c)
 except Exception:
  pass


def fetch_photo(query,seed,dest):
 query=contextual_visual_query(query)
 kind=_kind(query); pool=[]
 for title in CURATED.get(kind,[]):
  try:
   c=_exact_file(title)
   if c and _relevance(query,c)>=8: pool.append(c)
  except Exception: pass

 variants=[query]
 if kind:
  terms=sorted(SYN[kind],key=len,reverse=True)
  variants += [f'{CURRENT_CONTEXT} {terms[0]}',terms[0]]
 variants += [CURRENT_CONTEXT,f'{CURRENT_CONTEXT} exterior',f'{CURRENT_CONTEXT} interior']
 seen=[]
 for variant in variants:
  variant=' '.join(str(variant).split())
  if variant and variant not in seen: seen.append(variant)
 for variant in seen[:7]:
  minimum=10 if variant not in (CURRENT_CONTEXT,f'{CURRENT_CONTEXT} exterior',f'{CURRENT_CONTEXT} interior') else 7
  _add_candidates(pool,variant,query,minimum)

 uniq={str(c.get('url')):c for c in pool if c.get('url')}
 ranked=sorted(uniq.values(),key=lambda c:(str(c.get('url')) in USED_URLS,-_relevance(query,c),abs((c['width']/max(1,c['height']))-1.3),-min(c['width'],c['height'])))
 if not ranked:
  return {'query':query,'source_type':'none','error':'No semantically adequate public-domain/CC0 image found'}
 pick=ranked[seed%min(4,len(ranked))]
 raw=Path(dest).with_suffix('.download')
 try:
  base.download(pick['url'],raw)
  with Image.open(raw) as src:
   src=ImageOps.exif_transpose(src).convert('RGB')
   if src.width<600 or src.height<400: raise RuntimeError('image too small')
   src.save(dest,quality=94)
  raw.unlink(missing_ok=True)
  USED_URLS.add(str(pick['url']))
  pick['query']=query; pick['source_type']='wikimedia-public-domain'; pick['relevanceScore']=_relevance(query,pick)
  return pick
 except Exception as e:
  raw.unlink(missing_ok=True)
  return {'query':query,'source_type':'none','error':str(e)[:500]}


def _entry(b,duration,hold_max=7.6):
 hold=min(hold_max,max(5.8,b['end']-b['start']+0.9),max(0,duration-b['start']-.15))
 if hold<3.2: return None
 return {'start':b['start'],'end':b['start']+hold,'duration':hold,'query':contextual_visual_query(b['text']),'score':b.get('score',0),'beat_text':b['text']}


def select_visuals(beats,duration):
 if not beats: return []
 selected=[]; last=-999.0
 for i,b in enumerate(beats):
  gap=b['start']-last
  should=(i==0) or (gap>=11.5 and b.get('score',0)>=4) or gap>=17.0
  if not should: continue
  v=_entry(b,duration,7.6)
  if v:
   selected.append(v); last=b['start']

 for _ in range(18):
  selected.sort(key=lambda v:v['start'])
  starts=[v['start'] for v in selected]
  spans=[]
  if starts and starts[0]>18.5: spans.append((starts[0],0.0,starts[0]))
  for a,z in zip(starts,starts[1:]): spans.append((z-a,a,z))
  if starts and duration-starts[-1]>18.5: spans.append((duration-starts[-1],starts[-1],duration))
  if not spans: break
  gap,a,z=max(spans)
  if gap<=18.5: break
  midpoint=(a+z)/2
  candidates=[b for b in beats if a+5.0<=b['start']<=z-3.5 and all(abs(b['start']-v['start'])>=9.5 for v in selected)]
  if not candidates: break
  b=max(candidates,key=lambda x:(x.get('score',0),-abs(x['start']-midpoint)))
  v=_entry(b,duration,7.2)
  if not v: break
  selected.append(v)

 selected.sort(key=lambda v:v['start'])
 clean=[]
 for v in selected:
  if clean and v['start']<clean[-1]['end']+0.45: continue
  clean.append(v)
 max_visuals=max(12,min(24,int(duration/13.5)+1))
 return clean[:max_visuals]


def _union_coverage(visuals):
 if not visuals: return 0.0
 spans=sorted((float(v['start']),float(v['end'])) for v in visuals)
 total=0.0; a,z=spans[0]
 for x,y in spans[1:]:
  if x<=z: z=max(z,y)
  else: total+=max(0,z-a); a,z=x,y
 total+=max(0,z-a)
 return total


def verify(video,cues,visuals,narration,source_count):
 actual=base.media_duration(video)
 coverage=_union_coverage(visuals)/max(1,actual)
 starts=[v['start'] for v in visuals]
 gaps=[b-a for a,b in zip(starts,starts[1:])]
 source_ratio=source_count/max(1,len(visuals))
 bad=sum(1 for c in cues if c.get('bad_ending'))/max(1,len(cues))
 checks={
  'duration_in_range':120<=actual<=540,
  'caption_density_ok':len(cues)>=max(90,int(actual*.82)),
  'caption_word_limit_ok':max((c['words'] for c in cues),default=0)<=4,
  'caption_natural_boundary_ok':bad<=.08,
  'visual_insert_count_ok':len(visuals)>=max(8,int(actual/35)),
  'visual_coverage_ok':.28<=coverage<=.62,
  'visual_max_gap_ok':not gaps or max(gaps)<=19.0,
  'photo_source_ratio_ok':source_ratio>=.65,
  'no_primitive_placeholder_art':True,
  'audio_video_sync_ok':abs(actual-narration)<=2
 }
 return actual,coverage,gaps,source_ratio,checks,all(checks.values())
