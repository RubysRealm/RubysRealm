#!/usr/bin/env python3
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from votify.api.api import SpotifyApi
from votify.api.enums import SessionType

STATE_PATH = Path('rubyclips/muffin_state.json')
QUEUE_PATH = Path('rubyclips/spotify_episode_queue.json')


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def episode_from_item(item):
    entity = (item or {}).get('entity') or {}
    data = entity.get('data') or {}
    uri = str(entity.get('_uri') or entity.get('uri') or data.get('uri') or '')
    episode_id = uri.rsplit(':', 1)[-1] if uri.startswith('spotify:episode:') else ''
    release = data.get('releaseDate') or {}
    return episode_id, {
        'title': str(data.get('name') or entity.get('name') or '').strip(),
        'releaseDate': str(release.get('isoString') or data.get('releaseDate') or ''),
    }


async def fetch_episode(api, episode_id, feed_index, hints, sem):
    data = {}
    try:
        async with sem:
            response = await api.get_episode(episode_id)
        data = response['data']['episodeUnionV2']
    except Exception as exc:
        print(f'Episode metadata fallback for {episode_id}: {exc}')
    release = data.get('releaseDate') or {}
    release_iso = str(release.get('isoString') or hints.get('releaseDate') or '')
    title = str(data.get('name') or hints.get('title') or f'Spotify episode {episode_id}').strip()
    return {
        'id': episode_id,
        'title': title,
        'releaseDate': release_iso,
        'url': f'https://open.spotify.com/episode/{episode_id}',
        'sourceFeedIndexNewestFirst': int(feed_index),
    }


async def load_catalog(show_id):
    api = await SpotifyApi.create(session_type=SessionType.WEB)
    try:
        response = await api.get_show(show_id, offset=0, limit=300)
        show_data = response['data']['podcastUnionV2']
        items = list((show_data.get('episodesV2') or {}).get('items') or [])
        total = int((show_data.get('episodesV2') or {}).get('totalCount') or len(items))
        while len(items) < total:
            page = await api.get_show(show_id, offset=len(items), limit=min(300, total-len(items)))
            more = list((page['data']['podcastUnionV2'].get('episodesV2') or {}).get('items') or [])
            if not more:
                break
            items.extend(more)

        ids = []
        seen = set()
        for idx, item in enumerate(items):
            eid, hints = episode_from_item(item)
            if eid and eid not in seen:
                seen.add(eid)
                ids.append((eid, idx, hints))

        if not ids:
            raise RuntimeError('Spotify show returned no episode ids.')

        sem = asyncio.Semaphore(8)
        episodes = await asyncio.gather(*(fetch_episode(api, eid, idx, hints, sem) for eid, idx, hints in ids))
        # Spotify's show feed is newest-first. Reversing that source order is the
        # authoritative chronological queue and remains correct even when an
        # individual episode has missing/partial release-date metadata.
        episodes.sort(key=lambda e: -int(e.get('sourceFeedIndexNewestFirst', 0)))
        for position, ep in enumerate(episodes, start=1):
            ep['position'] = position
        return show_data, episodes
    finally:
        await api.client.aclose()


async def main():
    state = json.loads(STATE_PATH.read_text())
    if str(state.get('sourceProvider') or '').lower() != 'spotify-show':
        print('Spotify source sync not active; leaving queue unchanged.')
        return

    show_id = str(state.get('spotifyShowId') or '').strip()
    if not show_id:
        raise SystemExit('spotifyShowId is missing from muffin_state.json.')

    old_queue = {}
    if QUEUE_PATH.exists():
        old_queue = json.loads(QUEUE_PATH.read_text())

    show_data, catalog = await load_catalog(show_id)
    catalog_ids = {ep['id'] for ep in catalog}

    completed = {str(x) for x in old_queue.get('completedEpisodeIds', []) if str(x) in catalog_ids}
    prior_current = str(old_queue.get('currentEpisodeId') or '')

    # Once the active episode has actually completed, mark it complete before advancing.
    state_current = str(state.get('currentSeriesId') or '')
    if old_queue and bool(state.get('currentSeriesComplete')) and state_current in catalog_ids:
        completed.add(state_current)

    # First migration intentionally starts from the oldest episode. Later syncs preserve
    # an unfinished queue item and append newly discovered episodes at the back.
    if not old_queue:
        current_id = next((ep['id'] for ep in catalog if ep['id'] not in completed), '')
    elif prior_current and prior_current in catalog_ids and prior_current not in completed:
        current_id = prior_current
    else:
        current_id = next((ep['id'] for ep in catalog if ep['id'] not in completed), '')

    if not current_id:
        queue = {
            'version': 1,
            'showId': show_id,
            'showUrl': f'https://open.spotify.com/show/{show_id}',
            'showName': str(show_data.get('name') or state.get('spotifyCreator') or 'Spotify show'),
            'order': 'oldest-to-newest',
            'syncedAt': now_iso(),
            'episodeCount': len(catalog),
            'currentEpisodeId': None,
            'completedEpisodeIds': sorted(completed),
            'episodes': [{**ep, 'status': 'completed'} for ep in catalog],
        }
        QUEUE_PATH.write_text(json.dumps(queue, indent=2) + '\n')
        print(f'All {len(catalog)} Spotify episodes are complete.')
        return

    queue_episodes = []
    for ep in catalog:
        status = 'completed' if ep['id'] in completed else ('current' if ep['id'] == current_id else 'pending')
        queue_episodes.append({**ep, 'status': status})

    current = next(ep for ep in queue_episodes if ep['id'] == current_id)
    queue = {
        'version': 1,
        'showId': show_id,
        'showUrl': f'https://open.spotify.com/show/{show_id}',
        'showName': str(show_data.get('name') or state.get('spotifyCreator') or 'Spotify show'),
        'order': 'oldest-to-newest',
        'syncedAt': now_iso(),
        'episodeCount': len(queue_episodes),
        'currentEpisodeId': current_id,
        'currentPosition': int(current['position']),
        'completedEpisodeIds': sorted(completed),
        'episodes': queue_episodes,
    }
    QUEUE_PATH.write_text(json.dumps(queue, indent=2) + '\n')

    changed_episode = state_current != current_id
    if changed_episode:
        state['restartGeneration'] = int(state.get('restartGeneration') or 0) + 1
        state['nextEpisode'] = 1
        state['nextPart'] = 1
        state['lastPostedPart'] = 0
        state['lastPostedEpisodes'] = []
        state['currentSeriesComplete'] = False
        state['storyTotalParts'] = 1
        state['sourceDurationSeconds'] = 0
        state['lastLogicalPostKey'] = None
        state.pop('transportProvider', None)
        state.pop('transportUrl', None)
        state.pop('transportVideoId', None)
        state.pop('sourceDurationSeconds', None)

    state['currentSeriesId'] = current_id
    state['currentSeriesTitle'] = current['title']
    state['spotifyEpisodeUrl'] = current['url']
    state['sourceProvider'] = 'spotify-show'
    state['spotifyQueueFile'] = str(QUEUE_PATH)
    state['spotifyQueueOrder'] = 'oldest-to-newest'
    state['spotifyQueuePosition'] = int(current['position'])
    state['spotifyQueueTotal'] = len(queue_episodes)
    state['restartReason'] = (
        'Initialized BabyJamie Spotify queue oldest-to-newest.'
        if not old_queue else
        'Advanced/preserved BabyJamie Spotify queue in oldest-to-newest order.'
    )
    STATE_PATH.write_text(json.dumps(state, indent=2) + '\n')

    first = queue_episodes[0]
    last = queue_episodes[-1]
    print(json.dumps({
        'ok': True,
        'order': 'oldest-to-newest',
        'episodeCount': len(queue_episodes),
        'current': current,
        'oldest': first,
        'newest': last,
        'completedCount': len(completed),
    }, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
