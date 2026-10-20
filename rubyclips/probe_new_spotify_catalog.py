#!/usr/bin/env python3
import asyncio,json
from votify.api.api import SpotifyApi
from votify.api.enums import SessionType
SHOW_ID='6alyG1Jw4KH03mXZlYtPkf'

def eid(item):
    ent=(item or {}).get('entity') or {}
    data=ent.get('data') or {}
    uri=str(ent.get('_uri') or ent.get('uri') or data.get('uri') or '')
    return uri.rsplit(':',1)[-1] if uri.startswith('spotify:episode:') else ''

async def main():
    api=await SpotifyApi.create(session_type=SessionType.WEB)
    try:
        r=await api.get_show(SHOW_ID,offset=0,limit=300)
        show=r['data']['podcastUnionV2']
        items=list((show.get('episodesV2') or {}).get('items') or [])
        total=int((show.get('episodesV2') or {}).get('totalCount') or len(items))
        while len(items)<total:
            p=await api.get_show(SHOW_ID,offset=len(items),limit=min(300,total-len(items)))
            more=list((p['data']['podcastUnionV2'].get('episodesV2') or {}).get('items') or [])
            if not more: break
            items.extend(more)
        ids=[eid(x) for x in items if eid(x)]
        rows=[]
        for idx,xid in enumerate(ids):
            er=await api.get_episode(xid)
            e=er['data']['episodeUnionV2']
            rows.append({
                'id':xid,
                'title':str(e.get('name') or ''),
                'releaseDate':str((e.get('releaseDate') or {}).get('isoString') or ''),
                'description':str(e.get('description') or '')[:500],
                'mediaTypes':e.get('mediaTypes') or e.get('media_types') or [],
                'feedIndexNewestFirst':idx
            })
        rows.sort(key=lambda x:-x['feedIndexNewestFirst'])
        out={
            'showId':SHOW_ID,
            'showName':str(show.get('name') or ''),
            'publisher':str(show.get('publisher') or show.get('creator') or ''),
            'episodeCount':len(rows),
            'oldest':rows[:8],
            'newest':rows[-5:]
        }
        print(json.dumps(out,indent=2))
    finally:
        await api.client.aclose()
asyncio.run(main())
