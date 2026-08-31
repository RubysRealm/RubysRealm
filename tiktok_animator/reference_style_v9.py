import os
from pathlib import Path
from PIL import Image, ImageOps

_PIPE=None

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
            event=' '.join(str(beat).replace('\n',' ').split())[:340]
            prompt=(
                'Illustrate exactly this story event: '+event+'. '
                'Minimal polished flat 2D adult cartoon for a vertical mobile story. '
                'Character design is mandatory: very large smooth near-circular bald head, tiny black dot eyes, '
                'tiny short-line mouth, almost no nose, compact small body, short simple limbs, clean bold outline, '
                'simple geometric shapes, restrained facial detail, friendly deadpan expression. '
                'The CURRENT EVENT is the highest priority: show the exact action, exact location, and the specific important objects named in it; do not substitute generic buildings, phones, desks, keys, or repeated props unless the event explicitly calls for them. '
                'Show the character actively doing the narrated action inside a specific detailed illustrated environment; vary location, props, composition and camera angle from scene to scene, with a strong readable silhouette. '
                'Flat cel colors with subtle two-tone shading, crisp digital vector-cartoon finish. One scene only. '
                'Absolutely no realistic anatomy, no normal human proportions, no detailed eyes, no large eyes, no long nose, '
                'no realistic face, no photography, no 3D, no anime, no painterly style, no collage, no split screen, no text, no watermark.'
            )
            gen=torch.Generator(device='cpu').manual_seed(int(seed)&0x7fffffff)
            image=_PIPE(prompt=prompt,guidance_scale=0.0,num_inference_steps=int(os.getenv('LOCAL_CARTOON_STEPS','4')),height=512,width=512,generator=gen).images[0]
            image=ImageOps.fit(image.convert('RGB'),(1024,1280),method=Image.Resampling.LANCZOS)
            image.save(dest,'JPEG',quality=95)
            return {'query':str(beat)[:500],'source_type':'ai-generated-illustration','model':model,'via':'local-sdxl-turbo-reference-v9-text2image','seed':int(seed),'visualStyle':'hotel-owner-reference-minimal-round-head-2d'}
        except Exception as e:
            Path(dest).unlink(missing_ok=True)
            print('Reference v9 SDXL generation failed:',str(e)[:500])
            return None
    target._ai_image=reference_image
