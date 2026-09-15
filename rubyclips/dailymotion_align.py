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
    e=np.sqrt(np.mean(x*x,axis=1)+1e-12)
    e=np.log1p(e*1000.0)
    return e

def z(x):
    x=np.asarray(x,dtype=np.float64)
    s=x.std()
    return (x-x.mean())/(s if s>1e-9 else 1.0)

def best_match(full, pattern):
    p=z(pattern)
    n=len(full); m=len(p)
    size=1
    while size < n+m-1: size <<= 1
    F=np.fft.rfft(full-full.mean(),size)
    P=np.fft.rfft(p[::-1],size)
    corr=np.fft.irfft(F*P,size)[m-1:n]
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

# The old short-clip logic accidentally started both validation windows at ~54s.
# Use genuinely separated windows, biased toward the tail because Part 12 must
# begin immediately after the end of Part 11 in the full-story source.
window_specs=[
    ('early', max(8.0, part_d*0.12), min(28.0, part_d*0.18)),
    ('middle', max(20.0, part_d*0.43), min(28.0, part_d*0.18)),
    ('late', max(35.0, part_d*0.72), min(28.0, part_d*0.18)),
]
windows=[]
for label,start_s,length_s in window_specs:
    # Keep every sample window comfortably inside the clip.
    if start_s + length_s > part_d - 3.0:
        start_s=max(3.0, part_d - length_s - 3.0)
    a=int(start_s*hz); b=min(len(part),a+int(length_s*hz))
    if b-a<100:
        continue
    idx,score=best_match(full,part[a:b])
    match_s=idx/hz
    inferred_start=match_s-start_s
    inferred_end=inferred_start+part_d
    windows.append({
        'label':label,
        'partWindowStart':start_s,
        'partWindowLength':length_s,
        'matchFullTime':match_s,
        'inferredPartStart':inferred_start,
        'inferredPartEnd':inferred_end,
        'score':score,
    })

# Prefer the two closest high-confidence offsets. This tolerates one bad match
# caused by an episode boundary, intro/outro, or mastering difference.
eligible=[w for w in windows if w['score'] >= 0.15]
best_pair=None
for i in range(len(eligible)):
    for j in range(i+1,len(eligible)):
        a,b=eligible[i],eligible[j]
        spread=abs(a['inferredPartStart']-b['inferredPartStart'])
        quality=a['score']+b['score']
        candidate=(spread,-quality,a,b)
        if best_pair is None or candidate[:2] < best_pair[:2]:
            best_pair=candidate

alignment_ok=False
used=[]
spread=999999.0
if best_pair is not None and best_pair[0] <= 8.0:
    spread=best_pair[0]
    used=[best_pair[2],best_pair[3]]
    # Weight toward the later window when deriving the continuation boundary.
    weights=np.array([max(0.01,w['score']) for w in used],dtype=np.float64)
    starts=np.array([w['inferredPartStart'] for w in used],dtype=np.float64)
    part_start=float(np.average(starts,weights=weights))
    part_end=part_start+part_d
    alignment_ok=True
else:
    # If separated windows do not agree, a strong late-window match is safer
    # for continuation than the old median of contradictory matches.
    late=[w for w in windows if w['label']=='late' and w['score'] >= 0.30]
    if late:
        used=late
        part_start=float(late[0]['inferredPartStart'])
        part_end=float(late[0]['inferredPartEnd'])
        spread=0.0
        alignment_ok=True
    else:
        starts=[w['inferredPartStart'] for w in windows]
        part_start=float(np.median(starts)) if starts else -1.0
        part_end=part_start+part_d

remaining=full_d-part_end
alignment_ok=bool(alignment_ok and part_start>=0 and part_end<=full_d+3)
result={
    'fullDuration':full_d,
    'part11Duration':part_d,
    'part11StartInFull':part_start,
    'part11EndInFull':part_end,
    'remainingSeconds':remaining,
    'windowMatches':windows,
    'usedMatches':[w['label'] for w in used],
    'startSpreadSeconds':spread,
    'alignmentAcceptable':alignment_ok,
}
pathlib.Path(OUT).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['alignmentAcceptable']:
    raise SystemExit('Alignment confidence check failed')
