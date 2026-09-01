import os, re
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw, ImageFilter

_PIPE=None

def _keywords(text):
    t=' '+re.sub(r'[^a-z0-9]+',' ',str(text).lower())+' '
    return {
        'ticket': any(x in t for x in (' ticket ',' lottery ',' scan ',' numbers ')),
        'phone': any(x in t for x in (' phone ',' call ',' message ',' photograph ',' photo ')),
        'paper': any(x in t for x in (' attorney ',' accountant ',' paperwork ',' form ',' sign ',' mortgage ',' debt ',' document ')),
        'car': any(x in t for x in (' truck ',' car ',' dealership ',' drive ',' vehicle ')),
        'money': any(x in t for x in (' jackpot ',' cash ',' money ',' funds ',' bank ',' balance ',' payment ')),
        'travel': any(x in t for x in (' vacation ',' flight ',' hotel ',' balcony ',' room ')),
        'clerk': any(x in t for x in (' clerk ',' retailer ',' counter ')),
        'office': any(x in t for x in (' attorney ',' accountant ',' conference room ',' lottery office ')),
    }

def _avatar(size, x, y, scale=1.0, suit=False, pose='neutral', facing=1, secondary=False):
    layer=Image.new('RGBA',size,(0,0,0,0))
    d=ImageDraw.Draw(layer,'RGBA')
    s=scale
    def B(a,b,c,e): return (int(x+a*s),int(y+b*s),int(x+c*s),int(y+e*s))
    skin=(234,205,179,255) if not secondary else (210,166,132,255)
    skin2=(247,220,197,255) if not secondary else (226,184,149,255)
    shirt=(31,34,40,255) if suit else ((28,39,55,255) if not secondary else (68,99,132,255))
    pants=(28,29,34,255)
    shadow=Image.new('RGBA',size,(0,0,0,0)); sd=ImageDraw.Draw(shadow,'RGBA')
    sd.ellipse(B(-75,245,80,285),fill=(0,0,0,65)); shadow=shadow.filter(ImageFilter.GaussianBlur(max(5,int(10*s)))); layer.alpha_composite(shadow)
    d.rounded_rectangle(B(-48,128,-8,252),radius=max(6,int(13*s)),fill=pants)
    d.rounded_rectangle(B(10,128,50,252),radius=max(6,int(13*s)),fill=pants)
    d.ellipse(B(-61,235,-1,267),fill=(18,20,24,255)); d.ellipse(B(1,235,64,267),fill=(18,20,24,255))
    d.rounded_rectangle(B(-72,25,72,158),radius=max(10,int(32*s)),fill=shirt)
    if suit:
        d.polygon([(x-10*s,y+30*s),(x,y+85*s),(x+10*s,y+30*s)],fill=(235,235,238,255))
        d.polygon([(x-4*s,y+42*s),(x,y+78*s),(x+4*s,y+42*s)],fill=(131,23,33,255))
        d.line((x,y+86*s,x,y+148*s),fill=(10,12,15,130),width=max(1,int(2*s)))
    # arms / pose
    if pose=='hold':
        d.rounded_rectangle(B(-78,50,-25,145),radius=max(7,int(18*s)),fill=shirt)
        d.rounded_rectangle(B(25,50,78,145),radius=max(7,int(18*s)),fill=shirt)
        d.ellipse(B(-35,116,-5,146),fill=skin); d.ellipse(B(5,116,35,146),fill=skin)
    elif pose=='point':
        d.rounded_rectangle(B(-78,48,-25,146),radius=max(7,int(18*s)),fill=shirt)
        d.rounded_rectangle(B(20,55,105,88),radius=max(7,int(15*s)),fill=shirt)
        d.ellipse(B(91,52,118,82),fill=skin)
        d.ellipse(B(-35,120,-5,150),fill=skin)
    else:
        d.rounded_rectangle(B(-88,47,-35,150),radius=max(7,int(18*s)),fill=shirt)
        d.rounded_rectangle(B(35,47,88,150),radius=max(7,int(18*s)),fill=shirt)
        d.ellipse(B(-91,136,-63,164),fill=skin); d.ellipse(B(63,136,91,164),fill=skin)
    # oversized bald head
    d.rounded_rectangle(B(-18,-3,18,32),radius=max(4,int(8*s)),fill=skin)
    d.ellipse(B(-70,-105,70,35),fill=skin)
    d.ellipse(B(-58,-94,61,23),fill=skin2)
    d.ellipse(B(-80,-55,-58,-22),fill=skin); d.ellipse(B(58,-55,80,-22),fill=skin)
    ey=-43
    shift=5 if facing>0 else -5
    d.ellipse(B(-25+shift,ey,-13+shift,ey+12),fill=(28,28,31,255))
    d.ellipse(B(15+shift,ey,27+shift,ey+12),fill=(28,28,31,255))
    d.line((x-18*s,y-11*s,x+20*s,y-11*s),fill=(70,56,51,230),width=max(2,int(3*s)))
    d.arc(B(-58,-91,60,27),205,330,fill=(255,255,255,90),width=max(2,int(3*s)))
    return layer

def _prop(layer, kind, x, y, s=1.0):
    d=ImageDraw.Draw(layer,'RGBA')
    def B(a,b,c,e): return (int(x+a*s),int(y+b*s),int(x+c*s),int(y+e*s))
    if kind=='ticket':
        d.rounded_rectangle(B(-45,-24,45,24),radius=max(3,int(7*s)),fill=(246,244,220,255),outline=(30,30,35,255),width=max(1,int(2*s)))
        for i in range(5): d.ellipse(B(-28+i*13,-6,-22+i*13,0),fill=(55,55,60,255))
    elif kind=='phone':
        d.rounded_rectangle(B(-20,-38,20,38),radius=max(3,int(6*s)),fill=(25,27,31,255))
        d.rounded_rectangle(B(-15,-29,15,25),radius=max(2,int(4*s)),fill=(112,181,218,255))
    elif kind=='paper':
        d.polygon([(x-38*s,y-28*s),(x+30*s,y-24*s),(x+35*s,y+30*s),(x-32*s,y+28*s)],fill=(244,239,214,255))
        for yy in (-12,0,12): d.line((x-20*s,y+yy*s,x+18*s,y+yy*s),fill=(95,95,100,180),width=max(1,int(2*s)))
    elif kind=='money':
        for k in range(3):
            d.rounded_rectangle(B(-42+k*5,-18-k*4,42+k*5,18-k*4),radius=max(2,int(4*s)),fill=(102,181,107,255),outline=(47,110,58,255),width=max(1,int(2*s)))

def _background_prompt(event):
    return (
        'Polished flat 2D editorial cartoon background and props for a vertical mobile story. '
        'NO PEOPLE, NO HUMANS, NO CHARACTERS. The exact current narrated beat is: '+event+'. '
        'Show the precise location and physical objects needed for this beat only. Do not foreshadow later events and do not repeat generic props from earlier scenes. '
        'Use clean bold outlines, simple geometric forms, colorful cel shading, crisp mobile-friendly composition, strong foreground/midground/background depth. '
        'No readable text, no logos, no watermark, no collage, no split screen, no photorealism, no 3D, no anime.'
    )

def _scene_layout(event):
    k=_keywords(event)
    if k['clerk']: return ('hold','ticket',True)
    if 'sign' in event.lower(): return ('hold','paper',False)
    if 'photograph' in event.lower() or 'photo' in event.lower(): return ('hold','phone',False)
    if k['paper']: return ('hold','paper',True)
    if k['ticket']: return ('hold','ticket',False)
    if k['phone']: return ('hold','phone',False)
    if k['money']: return ('hold','money',False)
    return ('neutral',None,False)

def bind(target):
    def reference_image(beat,seed,dest):
        global _PIPE
        try:
            import torch
            from diffusers import AutoPipelineForText2Image
            model=os.getenv('LOCAL_CARTOON_MODEL','stabilityai/sdxl-turbo')
            if _PIPE is None:
                _PIPE=AutoPipelineForText2Image.from_pretrained(model,torch_dtype=torch.float32,use_safetensors=True)
                try: _PIPE.enable_attention_slicing()
                except Exception: pass
                _PIPE.set_progress_bar_config(disable=True)
                try: torch.set_num_threads(max(2,min(8,os.cpu_count() or 4)))
                except Exception: pass
            event=' '.join(str(beat).replace('\n',' ').split())[:420]
            gen=torch.Generator(device='cpu').manual_seed(int(seed)&0x7fffffff)
            bg=_PIPE(prompt=('High-quality polished story illustration matching the approved Ruby\'s Realm reference image: oversized bald adult cartoon character, tiny dot-like eyes, minimal mouth and nose, compact body, clean black linework, sophisticated cel shading, detailed cinematic environment, strong depth and lighting. Depict LITERALLY and ONLY this exact current narrated event: '+event+'. Every named person, object, action and location must be visibly represented. Do not anticipate later narration. Change staging and environment with the beat. One coherent scene, no collage, no readable text, no watermark.'),guidance_scale=0.0,num_inference_steps=int(os.getenv('LOCAL_CARTOON_STEPS','4')),height=512,width=512,generator=gen).images[0]
            bg=ImageOps.fit(bg.convert('RGB'),(1024,1280),method=Image.Resampling.LANCZOS).convert('RGBA')
            pose,prop,second=_scene_layout(event)
            # consistent reusable SuperMii-like protagonist sprite, not redrawn by AI
            hero=_avatar(bg.size,340,710,1.34,suit=('attorney' in event.lower() or 'lottery office' in event.lower()),pose=pose,facing=1)
            bg.alpha_composite(hero)
            if second:
                other=_avatar(bg.size,735,735,1.12,suit=('attorney' in event.lower() or 'accountant' in event.lower()),pose='point',facing=-1,secondary=True)
                bg.alpha_composite(other)
            if prop:
                props=Image.new('RGBA',bg.size,(0,0,0,0))
                _prop(props,prop,430 if not second else 535,855,1.2)
                bg.alpha_composite(props)
            out=bg.convert('RGB')
            out.save(dest,'JPEG',quality=95)
            return {'query':str(beat)[:500],'source_type':'ai-generated-illustration','model':model,'via':'deterministic-avatar-plus-generated-background-v10','seed':int(seed),'visualStyle':'reusable-supermii-like-avatar-editorial-2d'}
        except Exception as e:
            Path(dest).unlink(missing_ok=True)
            print('Reference v10 composited generation failed:',str(e)[:500])
            return None
    target._ai_image=reference_image
