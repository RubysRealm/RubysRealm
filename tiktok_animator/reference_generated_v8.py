import json, os, urllib.request
from pathlib import Path
from PIL import Image, ImageOps

SERVICE_FAILURES=0


def bind(target):
    global SERVICE_FAILURES
    original_ai=target._ai_image
    original_verify=target.verify
    original_select=target.select_visuals

    def ai_image(beat,seed,dest):
        global SERVICE_FAILURES
        direct=original_ai(beat,seed,dest)
        if direct:
            return direct
        service=str(os.getenv('V7_IMAGE_SERVICE_URL','')).strip()
        token=str(os.getenv('GITHUB_OIDC_TOKEN','')).strip()
        if not service or not token:
            return None
        body=json.dumps({'title':target.CURRENT_TITLE,'beat':str(beat)[:1400],'index':int(seed)%25}).encode()
        last_error=None
        for _attempt in range(2):
            req=urllib.request.Request(service,data=body,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','User-Agent':'RubysRealmGitHubRenderer/8.1'})
            try:
                with urllib.request.urlopen(req,timeout=180) as r:
                    raw=r.read()
                    model=str(r.headers.get('X-Rubys-Realm-Image-Model') or 'vercel-ai-gateway')
                    balance=r.headers.get('X-Rubys-Realm-Credit-Balance-Before')
                Path(dest).write_bytes(raw)
                with Image.open(dest) as im:
                    im=ImageOps.exif_transpose(im).convert('RGB')
                    if im.width<600 or im.height<600:
                        raise RuntimeError('generated illustration too small')
                    im.save(dest,quality=95)
                source={'query':str(beat)[:500],'source_type':'ai-generated-illustration','model':model,'via':'vercel-oidc-image-service','seed':seed,'visualStyle':'non-photorealistic-3d-cartoon'}
                if balance is not None:
                    try: source['creditBalanceBefore']=round(float(balance),4)
                    except Exception: pass
                SERVICE_FAILURES=0
                return source
            except Exception as e:
                last_error=e
                Path(dest).unlink(missing_ok=True)
        SERVICE_FAILURES += 1
        print('Generated cartoon image unavailable for beat:',str(last_error)[:300])
        return None

    def prepare_visuals(visuals,seed,_semantic_fetch=None):
        valid=[]
        for i,v in enumerate(list(visuals)):
            dest=Path(target.base.__file__).parent/'tmp'/f'v8_cartoon_{i:02d}.jpg'
            dest.parent.mkdir(parents=True,exist_ok=True)
            beat=v.get('beat_text') or v.get('query') or target.CURRENT_TITLE
            source=target._ai_image(beat,seed+i*271,dest)
            v['source']=source or {'source_type':'none','query':str(beat)[:300]}
            if dest.exists() and (source or {}).get('source_type')=='ai-generated-illustration':
                v['photo']=dest
                valid.append(v)
        visuals[:] = valid
        if len(visuals)<10:
            raise RuntimeError(f'Only {len(visuals)} generated cartoon scenes completed; refusing realistic-photo fallback')
        visuals[0]['start']=0.0
        target.base.STYLE['generated_illustration_ratio']=1.0
        target.base.STYLE['visual_source_policy']='generated-cartoon-only'
        target.base.STYLE['photographic_fallback']='disabled'
        return len(visuals)

    def select_visuals(scheduler,semantic,beats,duration):
        visuals=list(original_select(scheduler,semantic,beats,duration))
        max_scenes=18
        if len(visuals)<=max_scenes:
            return visuals
        positions=[]
        for i in range(max_scenes):
            idx=round(i*(len(visuals)-1)/(max_scenes-1))
            if idx not in positions: positions.append(idx)
        return [visuals[i] for i in positions]

    def verify(video,cues,visuals,narration,source_count):
        actual,cov,gaps,ratio,checks,_passed=original_verify(video,cues,visuals,narration,source_count)
        sources=[v.get('source') or {} for v in visuals]
        generated=sum(1 for s in sources if s.get('source_type')=='ai-generated-illustration')
        generated_ratio=generated/max(1,len(visuals))
        checks['generated_illustration_ratio_ok']=generated_ratio==1.0 and len(visuals)>=10
        checks['no_realistic_photo_fallback_ok']=all(s.get('source_type')=='ai-generated-illustration' for s in sources)
        target.base.STYLE['generated_illustration_ratio']=round(generated_ratio,4)
        target.base.STYLE['visual_source_policy']='generated-cartoon-only'
        target.base.STYLE['photographic_fallback']='disabled'
        return actual,cov,gaps,ratio,checks,all(checks.values())

    target._ai_image=ai_image
    target.prepare_visuals=prepare_visuals
    target.select_visuals=select_visuals
    target.verify=verify
