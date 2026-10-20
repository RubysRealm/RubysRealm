#!/usr/bin/env python3
import asyncio, json, math, urllib.request, subprocess
from pathlib import Path
from votify.api.api import SpotifyApi
from votify.api.enums import SessionType

SHOW_ID='6alyG1Jw4KH03mXZlYtPkf'
OUT=Path('rubyclips/new_spotify_probe')
OUT.mkdir(parents=True,exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36'

def episode_id(item):
    ent=(item or {}).get('entity') or {}
    data=ent.get('data') or {}
    uri=str(ent.get('_uri') or ent.get('uri') or data.get('uri') or '')
    return uri.rsplit(':',1)[-1] if uri.startswith('spotify:episode:') else ''

async def main():
    api=await SpotifyApi.create(session_type=SessionType.WEB)
    try:
        show_resp=await api.get_show(SHOW_ID,offset=0,limit=300)
        show=show_resp['data']['podcastUnionV2']
        items=list((show.get('episodesV2') or {}).get('items') or [])
        total=int((show.get('episodesV2') or {}).get('totalCount') or len(items))
        while len(items)<total:
            page=await api.get_show(SHOW_ID,offset=len(items),limit=min(300,total-len(items)))
            more=list((page['data']['podcastUnionV2'].get('episodesV2') or {}).get('items') or [])
            if not more: break
            items.extend(more)
        ids=[episode_id(x) for x in items if episode_id(x)]
        if not ids: raise RuntimeError('show returned no episode ids')
        oldest_id=ids[-1]

        ep_resp=await api.get_episode(oldest_id)
        ep=ep_resp['data']['episodeUnionV2']
        title=str(ep.get('name') or '')
        release=((ep.get('releaseDate') or {}).get('isoString') or '')
        media_types=ep.get('mediaTypes') or ep.get('media_types') or []

        playback=await api.get_playback_info(oldest_id,'episode',['manifest_ids_video'])
        media=playback.get('media') or {}
        if not media:
            raise RuntimeError('Spotify playback API returned no media')
        item=next(iter(media.values()))
        video_uri=item.get('video_version_uri')
        if video_uri:
            item=media.get(video_uri) or item
        ids_video=((item.get('manifest') or {}).get('manifest_ids_video') or [])
        if not ids_video:
            raise RuntimeError('No native Spotify video manifest id')
        file_id=str(ids_video[0].get('file_id') or '')
        if not file_id:
            raise RuntimeError('Empty Spotify video manifest id')

        manifest=await api.get_video_manifest(file_id)
        contents=manifest.get('contents') or []
        if not contents: raise RuntimeError('Video manifest has no contents')
        content=contents[0]
        encrypted=bool(content.get('encryption_infos'))
        profiles=content.get('profiles') or []
        videos=[p for p in profiles if str(p.get('mime_type') or '')=='video/mp4']
        audios=[p for p in profiles if str(p.get('mime_type') or '')=='audio/mp4']
        if encrypted:
            raise RuntimeError('Native Spotify video manifest is encrypted')
        if not videos or not audios:
            raise RuntimeError('Native Spotify manifest lacks MP4 video/audio')

        vids=[p for p in videos if int(p.get('video_height') or 0)<=720] or videos
        video=max(vids,key=lambda p:(int(p.get('video_height') or 0),int(p.get('video_bitrate') or 0)))
        audio=max(audios,key=lambda p:int(p.get('audio_bitrate') or 0))

        base_urls=manifest.get('base_urls') or []
        init_tpl=str(manifest.get('initialization_template') or '')
        seg_tpl=str(manifest.get('segment_template') or '')
        seg_len=int(content.get('segment_length') or 0)
        full_duration=float(content.get('end_time_millis') or 0)/1000.0
        if not base_urls or not init_tpl or not seg_tpl or seg_len<=0 or full_duration<30:
            raise RuntimeError('Native manifest missing timing/templates')

        base_url=str(base_urls[0])
        sample_start=0.0
        sample_len=min(45.0,full_duration)
        first_ts=int(math.floor(sample_start/seg_len)*seg_len)
        last_ts=int(math.ceil((sample_start+sample_len)/seg_len)*seg_len)

        def urls_for(profile):
            pid=str(profile['id']); ftype=str(profile['file_type'])
            init=init_tpl.replace('{{profile_id}}',pid).replace('{{file_type}}',ftype)
            urls=[base_url+init]
            for ts in range(first_ts,last_ts+seg_len,seg_len):
                seg=seg_tpl.replace('{{profile_id}}',pid).replace('{{segment_timestamp}}',str(ts)).replace('{{file_type}}',ftype)
                urls.append(base_url+seg)
            return urls

        def bundle(urls,dest):
            with dest.open('wb') as fh:
                for u in urls:
                    req=urllib.request.Request(u,headers={'User-Agent':UA,'Accept':'*/*'})
                    with urllib.request.urlopen(req,timeout=90) as resp:
                        data=resp.read()
                    if len(data)<128:
                        raise RuntimeError('Spotify fragment too small')
                    fh.write(data)

        vf=OUT/'video.mp4'; af=OUT/'audio.mp4'; sample=OUT/'native-sample.mp4'
        bundle(urls_for(video),vf); bundle(urls_for(audio),af)

        subprocess.run([
            'ffmpeg','-y','-hide_banner','-loglevel','error',
            '-i',str(vf),'-i',str(af),'-t',f'{sample_len:.3f}',
            '-map','0:v:0','-map','1:a:0',
            '-c:v','libx264','-preset','veryfast','-crf','20','-pix_fmt','yuv420p',
            '-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(sample)
        ],check=True,timeout=900)

        probe=json.loads(subprocess.check_output([
            'ffprobe','-v','error','-show_streams','-show_format','-of','json',str(sample)
        ],text=True))
        vids_out=[s for s in probe['streams'] if s['codec_type']=='video']
        auds_out=[s for s in probe['streams'] if s['codec_type']=='audio']
        assert vids_out and auds_out
        assert int(vids_out[0].get('width') or 0)>0 and int(vids_out[0].get('height') or 0)>0
        assert float(probe['format']['duration'])>20
        subprocess.run([
            'ffmpeg','-y','-hide_banner','-loglevel','error','-ss','8','-i',str(sample),'-frames:v','1',str(OUT/'frame.jpg')
        ],check=True,timeout=120)

        result={
            'ok':True,
            'showId':SHOW_ID,
            'showName':str(show.get('name') or ''),
            'episodeCount':len(ids),
            'oldestEpisodeId':oldest_id,
            'oldestTitle':title,
            'oldestReleaseDate':release,
            'mediaTypes':media_types,
            'nativeVideoManifestId':file_id,
            'encrypted':encrypted,
            'fullDurationSeconds':round(full_duration,3),
            'selectedVideoHeight':int(video.get('video_height') or 0),
            'selectedVideoBitrate':int(video.get('video_bitrate') or 0),
            'selectedAudioBitrate':int(audio.get('audio_bitrate') or 0),
            'sampleDurationSeconds':float(probe['format']['duration']),
            'sampleSizeBytes':int(probe['format']['size'])
        }
        (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:
        try: await api.client.aclose()
        except: pass

asyncio.run(main())
