def bind(patch):
    original_set_context = patch.set_context

    def set_context(title):
        original_set_context(title)
        low = str(title).lower()
        anchors = []
        if 'marina' in low: anchors = ['marina','boats','docks','harbor']
        elif 'drive-in' in low or 'drive in' in low: anchors = ['drive-in','movie','theater','screen']
        elif 'diner' in low: anchors = ['diner','restaurant','counter']
        elif 'mountain lodge' in low or 'lodge' in low: anchors = ['mountain','lodge','cabin','hotel']
        elif 'ferry' in low: anchors = ['ferry','terminal','dock','boat']
        if anchors:
            patch.CURRENT_CONTEXT = ' '.join(anchors)

    patch.set_context = set_context


def select_visuals(patch, beats, duration):
    selected = list(patch.select_visuals(beats, duration))
    if not beats:
        return selected

    def starts():
        return sorted(float(v['start']) for v in selected)

    # Fill the largest remaining start-to-start gaps with the nearest concrete beat.
    # Keep inserts intermittent and non-overlapping; this changes scheduling, not QC limits.
    for _ in range(24):
        selected.sort(key=lambda v: float(v['start']))
        ss = starts()
        spans = []
        if ss and ss[0] > 18.0:
            spans.append((ss[0], 0.0, ss[0]))
        for a, z in zip(ss, ss[1:]):
            spans.append((z-a, a, z))
        if ss and duration-ss[-1] > 18.0:
            spans.append((duration-ss[-1], ss[-1], duration))
        if not spans:
            break
        gap, a, z = max(spans)
        if gap <= 18.0:
            break

        midpoint = (a + z) / 2.0
        candidates = []
        for b in beats:
            t = float(b['start'])
            if not (a + 4.0 <= t <= z - 3.0):
                continue
            # Enough room for the typical 5.8-7.2s visual hold without crowding neighbors.
            if any(abs(t-float(v['start'])) < 7.8 for v in selected):
                continue
            candidates.append(b)
        if not candidates:
            # Relax only scheduling separation, never the actual QC threshold.
            for b in beats:
                t = float(b['start'])
                if a + 3.0 <= t <= z - 2.0 and all(abs(t-float(v['start'])) >= 7.2 for v in selected):
                    candidates.append(b)
        if not candidates:
            break

        b = max(candidates, key=lambda x: (x.get('score',0), -abs(float(x['start'])-midpoint)))
        v = patch._entry(b, duration, 6.8)
        if not v:
            break
        selected.append(v)

    selected.sort(key=lambda v: float(v['start']))
    clean = []
    for v in selected:
        if clean and float(v['start']) < float(clean[-1]['end']) + 0.35:
            continue
        clean.append(v)
    return clean[:28]
