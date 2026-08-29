import json, os, urllib.request
from pathlib import Path
from PIL import Image, ImageOps

SERVICE_DISABLED=False


def bind(target):
    global SERVICE_DISABLED
    original_ai=target._ai_image
    original_verify=target.verify
    original_select=target.select_visuals

    def ai_image(beat,seed,dest):
        global SERVICE_DISABLED
        # Keep direct GitHub AI Gateway support when configured.
        direct=original_ai(beat,seed,dest)
        if direct:
            return direct
        if SERVICE_DISABLED:
            return None
        service=str(os.getenv('V7_IMAGE_SERVICE_URL','')).strip()
        token=str(os.getenv('GITHUB_OIDC_TOKEN','')).strip()
        if not service or not token:
            SERVICE_DISABLED=True
            return None
        body=json.dumps({'title':target.CURRENT_TITLE,'beat':str(beat)[:1400],'index':int(seed)%25}).encode()
        req=urllib.request.Request(service,data=body,method='POST',headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','User-Agent':'RubysRealmGitHubRenderer/8.0'})
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
            source={'query':str(beat)[:500],'source_type':'ai-generated-illustration','model':model,'via':'vercel-oidc-image-service','seed':seed}
            if balance is not None:
                try: source['creditBalanceBefore']=round(float(balance),4)
                except Exception: pass
            return source
        except Exception as e:
            Path(dest).unlink(missing_ok=True)
            print('Protected generated-image service unavailable for this attempt:',str(e)[:300])
            # Do not repeat a broken service call dozens of times in one attempt. Workflow retry starts clean.
            SERVICE_DISABLED=True
            return None

    def select_visuals(scheduler,semantic,beats,duration):
        visuals=list(original_select(scheduler,semantic,beats,duration))
        max_scenes=18
        if len(visuals)<=max_scenes:
            return visuals
        # Keep coverage from beginning through ending instead of simply truncating later scenes.
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
        checks['generated_illustration_ratio_ok']=generated_ratio>=0.65
        target.base.STYLE['generated_illustration_ratio']=round(generated_ratio,4)
        return actual,cov,gaps,ratio,checks,all(checks.values())

    target._ai_image=ai_image
    target.select_visuals=select_visuals
    target.verify=verify
