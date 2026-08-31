def select_visuals(semantic, beats, duration):
    if not beats:
        return []
    ordered=sorted(beats,key=lambda b:float(b['start']))
    selected=[]
    last=-999.0
    i=0
    while i < len(ordered):
        if not selected:
            b=ordered[0]
        else:
            lo=last+8.0
            hi=last+13.5
            target=last+10.5
            window=[x for x in ordered if lo<=float(x['start'])<=hi]
            if window:
                b=max(window,key=lambda x:(float(x.get('score',0))*1.7-abs(float(x['start'])-target),-float(x['start'])))
            else:
                future=[x for x in ordered if float(x['start'])>last+6.5]
                if not future: break
                before=[x for x in future if float(x['start'])<=last+14.0]
                b=max(before,key=lambda x:(float(x.get('score',0)),-abs(float(x['start'])-target))) if before else future[0]
        start=float(b['start'])
        if selected and start-last<6.2:
            i=ordered.index(b)+1
            continue
        available=max(0.0,float(duration)-start-0.15)
        hold=min(9.5,max(6.0,float(b['end'])-start+0.6),available)
        if hold>=3.2:
            selected.append({'start':start,'end':start+hold,'duration':hold,'query':semantic.semantic_query(b['text']),'score':b.get('score',0),'beat_text':b['text']})
            last=start
        try:
            i=ordered.index(b)+1
        except ValueError:
            i+=1
        if last>=duration-10:
            break
    # Hard gap repair. Only insert when a true start-to-start gap exceeds the QC limit.
    for _ in range(8):
        selected.sort(key=lambda v:float(v['start']))
        gaps=[(float(z['start'])-float(a['start']),a,z) for a,z in zip(selected,selected[1:])]
        if not gaps: break
        gap,a,z=max(gaps,key=lambda x:x[0])
        if gap<=14.0: break
        target=(float(a['start'])+float(z['start']))/2
        candidates=[b for b in ordered if float(a['start'])+6.0<=float(b['start'])<=float(z['start'])-6.0]
        if not candidates: break
        b=max(candidates,key=lambda x:(float(x.get('score',0))*1.5-abs(float(x['start'])-target)))
        st=float(b['start']); hold=min(9.0,max(5.8,float(b['end'])-st+0.5),max(0.0,duration-st-0.15))
        if hold<3.2: break
        selected.append({'start':st,'end':st+hold,'duration':hold,'query':semantic.semantic_query(b['text']),'score':b.get('score',0),'beat_text':b['text']})
    selected.sort(key=lambda v:float(v['start']))
    clean=[]
    for v in selected:
        if clean and float(v['start'])-float(clean[-1]['start'])<6.0:
            if float(v.get('score',0))>float(clean[-1].get('score',0)): clean[-1]=v
            continue
        clean.append(v)
    return clean[:40]
