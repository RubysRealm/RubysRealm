import html, re
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
import reference_media as base

USED=set()
PROFILE={'name':'story','anchors':{'building','office','room'},'must':{'building','office','room'},'queries':['building interior','building exterior'],'banned':set()}

PROFILES=[
 (('marina',), {'name':'marina','anchors':{'marina','dock','harbor','boat','yacht','pier','slip'},'must':{'marina','dock','harbor','boat','yacht','pier'},'queries':['marina boats docks','harbor marina boats','marina pier'],'banned':{'saint','church','mosaic','carta','hotel','sands'}}),
 (('drive-in','drive in'), {'name':'drive-in theater','anchors':{'drive-in','theater','cinema','screen','movie'},'must':{'drive-in','theater','cinema','screen','movie'},'queries':['drive-in movie theater','drive-in theater screen','outdoor cinema screen'],'banned':{'driveway','residence','house','street','pass','ticket','poster','advertisement','program'}}),
 (('diner',), {'name':'diner','anchors':{'diner','restaurant','counter','cafe','booth'},'must':{'diner','restaurant','cafe'},'queries':['american diner interior','roadside diner exterior','diner counter booths'],'banned':set()}),
 (('mountain lodge','lodge'), {'name':'mountain lodge','anchors':{'lodge','cabin','hotel','resort','mountain'},'must':{'lodge','cabin','hotel','resort'},'queries':['mountain lodge exterior','mountain lodge interior','rustic lodge cabin'],'banned':{'dance','tribal'}}),
 (('ferry',), {'name':'ferry terminal','anchors':{'ferry','terminal','dock','boat','pier'},'must':{'ferry','terminal','dock','boat','pier'},'queries':['ferry terminal dock','ferry boat terminal','river ferry dock'],'banned':set()}),
 (('warehouse',), {'name':'warehouse','anchors':{'warehouse','industrial','factory','storage'},'must':{'warehouse','factory','industrial'},'queries':['industrial warehouse interior','warehouse exterior','warehouse loading bay'],'banned':set()}),
 (('radio station',), {'name':'radio station','anchors':{'radio','studio','broadcast','microphone','transmitter'},'must':{'radio','studio','broadcast','transmitter'},'queries':['radio station studio','broadcast radio studio','radio transmitter building'],'banned':set()}),
 (('greenhouse',), {'name':'greenhouse','anchors':{'greenhouse','nursery','plants','horticulture'},'must':{'greenhouse','nursery'},'queries':['commercial greenhouse interior','greenhouse plants','plant nursery greenhouse'],'banned':set()}),
 (('storage',), {'name':'storage facility','anchors':{'storage','warehouse','locker','unit'},'must':{'storage','warehouse','locker','unit'},'queries':['self storage facility','storage unit interior','self storage corridor'],'banned':set()}),
 (('theater',), {'name':'movie theater','anchors':{'theater','cinema','movie','screen','auditorium'},'must':{'theater','cinema','movie','auditorium'},'queries':['old movie theater interior','cinema auditorium','movie theater projection booth'],'banned':{'pass','ticket','poster'}}),
]

INTENTS=[
 ('camera', ('security camera','cctv','surveillance'), {'camera','cctv','surveillance'}, ['security camera CCTV','surveillance camera']),
 ('electrical', ('electrical panel','breaker','circuit panel','fuse box'), {'electrical','panel','breaker','circuit','fuse'}, ['electrical breaker panel','circuit breaker panel']),
 ('filing', ('filing cabinet','file cabinet'), {'filing','cabinet','files'}, ['filing cabinet office','metal filing cabinet']),
 ('ledger', ('ledger','account book'), {'ledger','accounting','book','records'}, ['old ledger book','accounting ledger book']),
 ('map', ('floor plan','parcel map','survey','map','blueprint'), {'map','plan','blueprint','survey','drawing'}, ['architectural floor plan','property survey map','building blueprint']),
 ('envelope', ('sealed envelope','envelope'), {'envelope','letter','mail'}, ['sealed envelope paper','paper envelope']),
 ('deed', ('deed','property records','ownership documents','contracts'), {'deed','document','contract','paper','records'}, ['property deed document','legal document papers']),
 ('police', ('sheriff','deputy','police','law enforcement'), {'sheriff','deputy','police','patrol'}, ['police patrol car','sheriff patrol vehicle']),
 ('key', ('key rack','key tag','brass key','keys','key'), {'key','keys','padlock','lock'}, ['brass key','vintage keys','key rack']),
 ('safe', ('safe','lockbox','cash box','fireproof box','document case','steel case'), {'safe','lockbox','case','box','vault'}, ['small safe lockbox','metal lock box','fireproof document box']),
 ('truck', ('pickup truck','box truck','tow truck','utility van','sedan','suv','vehicle'), {'truck','pickup','van','sedan','suv','vehicle','car'}, ['pickup truck','utility van parking lot','sedan parking lot']),
 ('phone', ('desk phone','telephone','intercom','phone'), {'telephone','phone','intercom'}, ['office desk telephone','old telephone','intercom speaker']),
 ('door', ('hidden door','door','corridor','hallway','passage'), {'door','corridor','hallway','passage'}, ['old building hallway door','narrow corridor doorway']),
 ('cash', ('cash','money'), {'cash','money','currency','banknote'}, ['cash banknotes envelope','paper money cash']),
 ('receipt', ('receipt','receipts'), {'receipt','invoice','paper'}, ['paper receipt invoice','old receipt paper']),
]

STOP={'your','life','owner','manager','buyer','after','buying','closed','old','current','shown','several','before','years','someone','simple','answer','properties','always','finally','recent','entries','company','business','take','control','finish','says'}
NEGATIVE_GLOBAL={'logo','icon','clipart','cartoon','flag','coat of arms'}


def set_context(title):
 global PROFILE, USED
 low=str(title).lower()
 PROFILE={'name':'story','anchors':set(), 'must':set(), 'queries':['building interior','building exterior'],'banned':set()}
 for needles,p in PROFILES:
  if any(n in low for n in needles):
   PROFILE={'name':p['name'],'anchors':set(p['anchors']),'must':set(p['must']),'queries':list(p['queries']),'banned':set(p['banned'])}
   break
 if not PROFILE['anchors']:
  toks=[x for x in re.findall(r'[a-z0-9-]+',low) if x not in STOP and len(x)>3]
  PROFILE['anchors']=set(toks[:4]) or {'building'}
  PROFILE['must']=set(toks[:2]) or {'building'}
  PROFILE['name']=' '.join(toks[:4]) or 'building'
  PROFILE['queries']=[PROFILE['name']+' exterior',PROFILE['name']+' interior']
 USED=set()


def _text(c):
 return html.unescape((str(c.get('title',''))+' '+str(c.get('description',''))).lower())


def _intent(q):
 low=str(q).lower()
 for name,needles,positive,queries in INTENTS:
  if any(n in low for n in needles): return name,positive,queries
 return None,set(),[]


def semantic_query(text):
 low=str(text).lower()
 name,pos,queries=_intent(low)
 if name:
  return f"{PROFILE['name']} {queries[0]}"
 toks=[]
 for t in re.findall(r'[a-z][a-z0-9-]+',low):
  if t in STOP or len(t)<4: continue
  if t not in toks: toks.append(t)
 return ' '.join(([PROFILE['name']]+toks[:5]))


def _term_hit(text,term):
 return bool(re.search(r'\b'+re.escape(term)+r'\b',text))


def _score(query,c):
 text=_text(c)
 qtokens=set(re.findall(r'[a-z0-9-]+',str(query).lower()))-STOP
 name,positive,_=_intent(query)
 if any(x in text for x in NEGATIVE_GLOBAL): return -999
 if PROFILE['banned'] and any(_term_hit(text,x) for x in PROFILE['banned']): return -999
 if name=='police' and ('edward sheriff curtis' in text or 'chief joseph' in text or 'self portrait' in text): return -999
 if PROFILE['name']=='marina' and any(x in text for x in ('saint marina','carta marina','marina bay sands')): return -999
 if name and not any(_term_hit(text,x) for x in positive): return -999
 if not name and PROFILE['must'] and not any(_term_hit(text,x) for x in PROFILE['must']): return -999
 overlap=sum(1 for t in qtokens if len(t)>3 and _term_hit(text,t))
 context=sum(1 for t in PROFILE['anchors'] if _term_hit(text,t))
 intent_hits=sum(1 for t in positive if _term_hit(text,t))
 score=overlap*5+context*5+intent_hits*10
 if name and intent_hits>=1: score+=8
 if not name and context>=2: score+=8
 if any(x in text for x in ('drawing','engraving','painting','illustration')) and name not in ('map','deed'): score-=12
 if 'exterior' in query.lower() and 'exterior' in text: score+=5
 if 'interior' in query.lower() and 'interior' in text: score+=5
 return score


def _variants(query):
 name,pos,queries=_intent(query)
 out=[]
 if name:
  out.extend(queries)
  out.extend([f"{PROFILE['name']} {q}" for q in queries])
 else:
  out.append(query)
  out.extend(PROFILE['queries'])
 seen=[]
 for q in out:
  q=' '.join(str(q).split())
  if q and q not in seen: seen.append(q)
 return seen[:8]


def fetch_photo(query,seed,dest):
 q=semantic_query(query)
 pool=[]
 for variant in _variants(q):
  try:
   for c in base.wiki_candidates(variant):
    c.setdefault('description','')
    s=_score(q,c)
    if s>=12:
     c=dict(c); c['_semantic_score']=s; c['_search_variant']=variant; pool.append(c)
  except Exception:
   pass
 uniq={str(c.get('url')):c for c in pool if c.get('url')}
 ranked=sorted(uniq.values(),key=lambda c:(str(c.get('url')) in USED,-int(c.get('_semantic_score',0)),abs((int(c.get('width') or 1)/max(1,int(c.get('height') or 1)))-1.3),-min(int(c.get('width') or 0),int(c.get('height') or 0))))
 if not ranked:
  return {'query':q,'source_type':'none','error':'No semantically adequate public-domain/CC0 photo found'}
 candidates=[c for c in ranked if str(c.get('url')) not in USED] or ranked
 last_error='download failed'
 for pick in candidates[:8]:
  raw=Path(dest).with_suffix('.download')
  try:
   base.download(pick['url'],raw)
   with Image.open(raw) as im:
    im=ImageOps.exif_transpose(im).convert('RGB')
    if im.width<600 or im.height<400: raise RuntimeError('image too small')
    im=ImageEnhance.Contrast(im).enhance(1.04)
    im=ImageEnhance.Color(im).enhance(0.96)
    im.save(dest,quality=95)
   raw.unlink(missing_ok=True)
   USED.add(str(pick['url']))
   return {'title':pick.get('title'),'url':pick.get('url'),'source_page':pick.get('source_page'),'license':pick.get('license'),'artist':pick.get('artist'),'width':pick.get('width'),'height':pick.get('height'),'description':pick.get('description',''),'query':q,'searchVariant':pick.get('_search_variant'),'source_type':'wikimedia-public-domain','relevanceScore':int(pick.get('_semantic_score',0))}
  except Exception as e:
   last_error=str(e)[:300]
   raw.unlink(missing_ok=True)
 return {'query':q,'source_type':'none','error':last_error}


def verify(base_verify,video,cues,visuals,narration,source_count):
 actual,cov,gaps,ratio,checks,passed=base_verify(video,cues,visuals,narration,source_count)
 direct=[v.get('source') or {} for v in visuals if (v.get('source') or {}).get('source_type')=='wikimedia-public-domain']
 urls=[str(s.get('url')) for s in direct if s.get('url')]
 rel=[int(s.get('relevanceScore') or 0) for s in direct]
 checks['semantic_photo_match_ok']=bool(rel) and sum(1 for x in rel if x>=12)/max(1,len(rel))>=0.90
 checks['photo_variety_ok']=not urls or len(set(urls))/len(urls)>=0.75
 passed=all(checks.values())
 return actual,cov,gaps,ratio,checks,passed
