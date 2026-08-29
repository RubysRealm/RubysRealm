import re
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
import reference_media as base
import reference_semantic_v4 as core

EXACT_PATTERNS=[
 (r'\b(truck|van|sedan|suv|vehicle)\b','pickup truck'),
 (r'\b(keys?|keyrack|key-tag)\b','brass key'),
 (r'\b(camera|cctv|surveillance)\b','security camera CCTV'),
 (r'\b(sheriff|deputy|police|patrol)\b','police patrol car'),
 (r'\b(breaker|electrical panel|fuse box)\b','electrical breaker panel'),
 (r'\b(ledger|account book)\b','old ledger book'),
 (r'\b(filing cabinet|file cabinet)\b','filing cabinet office'),
 (r'\b(envelope|letter)\b','sealed envelope paper'),
 (r'\b(deed|contract|ownership document)\b','property deed document'),
 (r'\b(floor plan|blueprint|survey|parcel map|\bmap\b)\b','architectural floor plan'),
 (r'\b(lockbox|safe|cash box|steel case|fireproof box|floor compartment)\b','metal lock box safe'),
 (r'\b(phone|telephone|intercom)\b','office desk telephone'),
 (r'\b(corridor|hallway|passage|hidden door|doorway)\b','building hallway doorway'),
 (r'\b(cash|money|banknotes)\b','cash banknotes'),
 (r'\b(receipt|invoice)\b','paper receipt invoice'),
]

def set_context(title):
    core.set_context(title)

def semantic_query(text):
    low=str(text).lower()
    for pattern,q in EXACT_PATTERNS:
        if re.search(pattern,low):
            return f"{core.PROFILE['name']} {q}"
    return core.semantic_query(text)

def _context_score(c):
    text=(str(c.get('title',''))+' '+str(c.get('description',''))).lower()
    if core.PROFILE.get('banned') and any(re.search(r'\b'+re.escape(x)+r'\b',text) for x in core.PROFILE['banned']): return -999
    if core.PROFILE['name']=='marina' and any(x in text for x in ('saint marina','carta marina','marina bay sands')): return -999
    hits=sum(1 for x in core.PROFILE.get('anchors',set()) if re.search(r'\b'+re.escape(x)+r'\b',text))
    must=sum(1 for x in core.PROFILE.get('must',set()) if re.search(r'\b'+re.escape(x)+r'\b',text))
    if must<1: return -999
    score=10+hits*6+must*5
    if any(x in text for x in ('exterior','interior','building','facility','room','dock','cabin','warehouse','studio','greenhouse')): score+=5
    if any(x in text for x in ('logo','icon','poster','ticket','mosaic','coat of arms')): score-=20
    return score

def _download(c,dest):
    raw=Path(dest).with_suffix('.download')
    try:
        base.download(c['url'],raw)
        with Image.open(raw) as im:
            im=ImageOps.exif_transpose(im).convert('RGB')
            if im.width<600 or im.height<400: raise RuntimeError('image too small')
            im=ImageEnhance.Contrast(im).enhance(1.04)
            im=ImageEnhance.Color(im).enhance(0.96)
            im.save(dest,quality=95)
        raw.unlink(missing_ok=True)
        return True
    except Exception:
        raw.unlink(missing_ok=True)
        return False

def fetch_photo(query,seed,dest):
    q=semantic_query(query)
    direct=core.fetch_photo(q,seed,dest)
    if direct.get('source_type')=='wikimedia-public-domain':
        direct['matchLevel']='exact-or-object'
        return direct
    pool=[]
    for variant in core.PROFILE.get('queries',[]):
        try:
            for c in base.wiki_candidates(variant):
                c=dict(c); c.setdefault('description',''); s=_context_score(c)
                if s>=15 and c.get('url'):
                    c['_score']=s; c['_variant']=variant; pool.append(c)
        except Exception:
            pass
    uniq={str(c.get('url')):c for c in pool}
    ranked=sorted(uniq.values(),key=lambda c:(str(c.get('url')) in core.USED,-int(c.get('_score',0)),-min(int(c.get('width') or 0),int(c.get('height') or 0))))
    fresh=[c for c in ranked if str(c.get('url')) not in core.USED] or ranked
    for c in fresh[:10]:
        if not _download(c,dest): continue
        core.USED.add(str(c.get('url')))
        return {'title':c.get('title'),'url':c.get('url'),'source_page':c.get('source_page'),'license':c.get('license'),'artist':c.get('artist'),'width':c.get('width'),'height':c.get('height'),'description':c.get('description',''),'query':q,'searchVariant':c.get('_variant'),'source_type':'wikimedia-public-domain','relevanceScore':int(c.get('_score',18)),'matchLevel':'setting-context'}
    return direct

def verify(base_verify,video,cues,visuals,narration,source_count):
    actual,cov,gaps,ratio,checks,passed=base_verify(video,cues,visuals,narration,source_count)
    direct=[v.get('source') or {} for v in visuals if (v.get('source') or {}).get('source_type')=='wikimedia-public-domain']
    urls=[str(s.get('url')) for s in direct if s.get('url')]
    rel=[int(s.get('relevanceScore') or 0) for s in direct]
    exact=sum(1 for s in direct if s.get('matchLevel')=='exact-or-object')
    checks['semantic_photo_match_ok']=bool(rel) and sum(1 for x in rel if x>=12)/max(1,len(rel))>=0.95
    checks['photo_variety_ok']=not urls or len(set(urls))/len(urls)>=0.75
    checks['exact_visual_share_ok']=exact/max(1,len(direct))>=0.35
    return actual,cov,gaps,ratio,checks,all(checks.values())
