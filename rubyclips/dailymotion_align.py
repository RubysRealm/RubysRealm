#!/usr/bin/env python3
import json, subprocess, pathlib, sys

try:
    import numpy as np
except ModuleNotFoundError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', 'numpy'], check=True)
    import numpy as np

FULL='rubyclips/dm_full.mp4'
PART='rubyclips/dm_part11.mp4'
OUT='rubyclips/dailymotion_alignment.json'
RATE=1000
ENV=100  # 100 ms windows => 10 Hz envelope

def run(cmd):
    subprocess.run(cmd, check=True)

def duration(p):
    return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',p], text=True).strip())

def pcm(p, raw):
    run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',p,'-vn','-ac','1','-ar',str(RATE),'-f','f32le',raw])
    x=np.fromfile(raw,dtype=np.float32)
    n=(len(x)//ENV)*ENV
    x=x[:n].reshape(-1,ENV)
    # RMS-ish amplitude envelope, log-compressed for robustness to mastering/codec changes
    e=np.sqrt(np.mean(x*x,axis=1)+1e-12)
    e=np.log1p(e*1000.0)
    return e

def z(x):
    x=np.asarray(x,dtype=np.float64)
    s=x.std()
    return (x-x.mean())/(s if s>1e-9 else 1.0)

def best_match(full, pattern):
    # FFT convolution for normalized-pattern correlation; local energy normalization follows.
    p=z(pattern)
    n=len(full); m=len(p)
    size=1
    while size < n+m-1: size <<= 1
    F=np.fft.rfft(full-full.mean(),size)
    P=np.fft.rfft(p[::-1],size)
    corr=np.fft.irfft(F*P,size)[m-1:n]
    # local denominator: pattern already std-normalized, normalize by local full energy
    y=full-full.mean()
    cs=np.concatenate([[0.0],np.cumsum(y*y)])
    energy=np.sqrt(np.maximum(cs[m:]-cs[:-m],1e-12)*np.sum(p*p))
    corr=corr[:len(energy)]/energy
    i=int(np.argmax(corr))
    return i,float(corr[i])

full_d=duration(FULL); part_d=duration(PART)
full=pcm(FULL,'rubyclips/dm_full.raw')
part=pcm(PART,'rubyclips/dm_part11.raw')
hz=RATE/ENV

# Match two independent windows from Part 11 for cross-checking.
windows=[]
for label,start_s,length_s in [
    ('middle', max(10.0,part_d*0.35), min(90.0,part_d*0.35)),
    ('tail', max(10.0,part_d-100.0), min(80.0,max(20.0,part_d-20.0)))
]:
    a=int(start_s*hz); b=min(len(part),a+int(length_s*hz))
    if b-a<100: continue
    idx,score=best_match(full,part[a:b])
    match_s=idx/hz
    inferred_start=match_s-start_s
    windows.append({'label':label,'partWindowStart':start_s,'matchFullTime':match_s,'inferredPartStart':inferred_start,'score':score})

starts=[w['inferredPartStart'] for w in windows]
part_start=float(np.median(starts))
spread=max(starts)-min(starts) if len(starts)>1 else 0.0
part_end=part_start+part_d
remaining=full_d-part_end
result={
    'fullDuration':full_d,
    'part11Duration':part_d,
    'part11StartInFull':part_start,
    'part11EndInFull':part_end,
    'remainingSeconds':remaining,
    'windowMatches':windows,
    'startSpreadSeconds':spread,
    'alignmentAcceptable': bool(part_start>=0 and part_end<=full_d+3 and spread<5.0 and all(w['score']>0.15 for w in windows))
}
pathlib.Path(OUT).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['alignmentAcceptable']:
    raise SystemExit('Alignment confidence check failed')
