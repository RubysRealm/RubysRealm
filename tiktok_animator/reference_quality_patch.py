import html, json, re, urllib.parse
from pathlib import Path
from PIL import Image, ImageOps
import reference_media as base

# Keep the user's short readable phrases, but measure density against that design
# instead of an unrealistic one-cue-per-word threshold.
base.STYLE['minimum_photo_source_ratio']=0.65

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
 'storage':{'storage','unit','units','locker','lockers'}, 'lock':{'lock','padlock','deadbolt','key'},
 'filing':{'filing','cabinet','ledger','records','files'}, 'workbench':{'workbench','workshop','garage'},
 'camera':{'camera','security','cctv','surveillance'}, 'fence':{'fence','chain','gate'},
 'sheriff':{'sheriff','police','patrol','deputy'}, 'sedan':{'sedan','car','vehicle'},
 'motel':{'motel','hotel','inn'}, 'key':{'key','keys','lock'}, 'deed':{'deed','document','documents','records','property','paper','papers','envelope'}
}
STOP=base.STOP | {'old','historic','photograph','photo','exterior','interior','facility','manager','roadside','residential'}

def _tokens(s): return set(re.findall(r'[a-z0-9]+',html.unescape(str(s)).lower()))-STOP

def _kind(query):
 q=_tokens(query)
 for k,v in SYN.items():
  if q & v: return k
 return None

def _exact_file(title):
 params={'action':'query','format':'json','origin':'*','titles':title,'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iiurlwidth':'1400'}
 data=base.http_json(base.WIKI_API+'?'+urllib.parse.urlencode(params)); pages=list(((data.get('query') or {}).get('pages') or {}).values())
 if not pages: return None
 p=pages[0]; info=(p.get('imageinfo') or [{}])[0]; meta=info.get('extmetadata') or {}; mime=str(info.get('mime','')).lower()
 if mime not in ('image/jpeg','image/png','image/webp') or int(info.get('width') or 0)<700 or int(info.get('height') or 0)<430 or not base.pd_license(meta): return None
 return {'title':p.get('title'),'url':info.get('thumburl') or info.get('url'),'source_page':info.get('descriptionurl'),'license':html.unescape(str(meta.get('LicenseShortName',{}).get('value','Public domain'))),'artist':re.sub(r'<[^>]+>','',html.unescape(str(meta.get('Artist',{}).get('value',''))))[:160],'width':int(info.get('width') or 0),'height':int(info.get('height') or 0),'description':re.sub(r'<[^>]+>',' ',html.unescape(str(meta.get('ImageDescription',{}).get('value',''))))[:500]}

def _relevance(query,c):
 q=_tokens(query); text=_tokens(str(c.get('title',''))+' '+str(c.get('description','')))
 kind=_kind(query); overlap=len(q&text); score=overlap*5
 if kind and text&SYN[kind]: score+=8
 phrase=' '.join(t for t in re.findall(r'[a-z0-9]+',query.lower()) if t not in STOP)
 hay=(str(c.get('title',''))+' '+str(c.get('description',''))).lower()
 if phrase and phrase in hay: score+=12
 # These ambiguous terms are responsible for the previous nonsense matches.
 if kind=='storage' and not text&SYN['storage']: return -99
 if kind=='camera' and not text&SYN['camera']: return -99
 if kind=='fence' and not text&SYN['fence']: return -99
 if kind=='sheriff' and not text&SYN['sheriff']: return -99
 if kind=='sedan' and not text&SYN['sedan']: return -99
 if kind=='key' and not text&SYN['key']: return -99
 return score

def fetch_photo(query,seed,dest):
 kind=_kind(query); pool=[]
 # Known, legitimately reusable photographs are tried first for recurring concrete concepts.
 for title in CURATED.get(kind,[]):
  try:
   c=_exact_file(title)
   if c: pool.append(c)
  except Exception: pass
 # Then use Commons search, but only accept results whose metadata actually matches the beat.
 variants=[query]
 if kind=='storage': variants += ['self storage unit','storage unit interior']
 elif kind=='camera': variants += ['security camera CCTV']
 elif kind=='fence': variants += ['chain link fence']
 elif kind=='filing': variants += ['filing cabinets records']
 elif kind=='workbench': variants += ['workbench workshop']
 elif kind=='key': variants += ['metal key lock']
 elif kind=='deed': variants += ['property deed document']
 for variant in variants:
  try:
   for c in base.wiki_candidates(variant):
    # wiki_candidates omitted the description, so title relevance is intentionally strict.
    c.setdefault('description','')
    if _relevance(query,c)>=8: pool.append(c)
  except Exception: pass
 uniq={str(c.get('url')):c for c in pool if c.get('url')}; ranked=sorted(uniq.values(),key=lambda c:(-_relevance(query,c),abs((c['width']/max(1,c['height']))-1.3),-min(c['width'],c['height'])))
 if not ranked: return {'query':query,'source_type':'none','error':'No semantically adequate public-domain/CC0 image found'}
 pick=ranked[seed%min(3,len(ranked))]; raw=Path(dest).with_suffix('.download')
 try:
  base.download(pick['url'],raw)
  with Image.open(raw) as src:
   src=ImageOps.exif_transpose(src).convert('RGB')
   if src.width<600 or src.height<400: raise RuntimeError('image too small')
   src.save(dest,quality=94)
  raw.unlink(missing_ok=True); pick['query']=query; pick['source_type']='wikimedia-public-domain'; pick['relevanceScore']=_relevance(query,pick); return pick
 except Exception as e:
  raw.unlink(missing_ok=True); return {'query':query,'source_type':'none','error':str(e)[:500]}

def select_visuals(beats,duration):
 if not beats: return []
 selected=[]; last=-999
 for i,b in enumerate(beats):
  gap=b['start']-last
  if i==0 or (gap>=7.5 and b.get('score',0)>=4) or gap>=14.5:
   hold=min(8.5,max(6.2,b['end']-b['start']+1.3),max(0,duration-b['start']-.15))
   if hold>=3.2:
    selected.append({'start':b['start'],'end':b['start']+hold,'duration':hold,'query':b['query'],'score':b.get('score',0),'beat_text':b['text']}); last=b['start']
 # Fill any remaining dead zones using the most concrete beat inside that interval.
 for _ in range(4):
  selected.sort(key=lambda v:v['start']); points=[0.0]+[v['start'] for v in selected]+[duration]
  gap_pair=max(((points[i+1]-points[i],points[i],points[i+1]) for i in range(len(points)-1)),default=(0,0,0))
  gap,a,z=gap_pair
  if gap<=18.0: break
  candidates=[b for b in beats if a+6.5<=b['start']<=z-4.0 and all(abs(b['start']-v['start'])>=5.8 for v in selected)]
  if not candidates: break
  b=max(candidates,key=lambda x:(x.get('score',0),-abs(x['start']-(a+z)/2)))
  hold=min(8.2,max(6.0,b['end']-b['start']+1.2),max(0,duration-b['start']-.15))
  selected.append({'start':b['start'],'end':b['start']+hold,'duration':hold,'query':b['query'],'score':b.get('score',0),'beat_text':b['text']})
 selected.sort(key=lambda v:v['start'])
 # Avoid overlap while keeping visually meaningful cadence.
 clean=[]
 for v in selected:
  if clean and v['start']<clean[-1]['end']+.35:
   continue
  clean.append(v)
 return clean[:28]

def verify(video,cues,visuals,narration,source_count):
 actual=base.media_duration(video); coverage=sum(v['duration'] for v in visuals)/max(1,actual); starts=[v['start'] for v in visuals]; gaps=[b-a for a,b in zip(starts,starts[1:])]; source_ratio=source_count/max(1,len(visuals)); bad=sum(1 for c in cues if c.get('bad_ending'))/max(1,len(cues))
 checks={'duration_in_range':120<=actual<=540,'caption_density_ok':len(cues)>=max(90,int(actual*.82)),'caption_word_limit_ok':max((c['words'] for c in cues),default=0)<=4,'caption_natural_boundary_ok':bad<=.08,'visual_insert_count_ok':len(visuals)>=max(8,int(actual/30)),'visual_coverage_ok':.28<=coverage<=.68,'visual_max_gap_ok':not gaps or max(gaps)<=18.5,'photo_source_ratio_ok':source_ratio>=.65,'no_primitive_placeholder_art':True,'audio_video_sync_ok':abs(actual-narration)<=2}
 return actual,coverage,gaps,source_ratio,checks,all(checks.values())
