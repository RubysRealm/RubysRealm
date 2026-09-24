#!/usr/bin/env python3
import html
import json
import re
import urllib.request
from pathlib import Path

STATE_PATH = Path('rubyclips/muffin_state.json')
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140 Safari/537.36'


def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml',
    })
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read().decode('utf-8', 'replace')


def latest_episode(show_id):
    page = fetch(f'https://open.spotify.com/embed/show/{show_id}')
    episode_id = None
    for pattern in (
        r'https://open\.spotify\.com/episode/([A-Za-z0-9]+)',
        r'/episode/([A-Za-z0-9]+)',
        r'spotify:episode:([A-Za-z0-9]+)',
    ):
        m = re.search(pattern, page)
        if m:
            episode_id = m.group(1)
            break
    if not episode_id:
        raise RuntimeError('Spotify embed did not expose a latest episode id.')

    title = ''
    creator = ''
    m = re.search(r'<title[^>]*>(.*?)</title>', page, re.I | re.S)
    if m:
        raw = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        suffix = re.match(r'^(.*?)\s+-\s+(.+?)\s+\\|\s+Spotify\s*$', raw)
        if suffix:
            title = suffix.group(1).strip()
            creator = suffix.group(2).strip()
        else:
            title = re.sub(r'\s*\\|\s*Spotify\s*$', '', raw).strip()

    return episode_id, title, creator


state = json.loads(STATE_PATH.read_text())
if str(state.get('sourceProvider') or '').lower() != 'spotify-show':
    print('Spotify source sync not active; leaving queue unchanged.')
    raise SystemExit(0)

show_id = str(state.get('spotifyShowId') or '').strip()
if not show_id:
    raise SystemExit('spotifyShowId is missing from muffin_state.json.')

try:
    latest_id, latest_title, latest_creator = latest_episode(show_id)
except Exception as exc:
    print(f'Spotify catalog discovery unavailable; keeping current episode: {exc}')
    raise SystemExit(0)

current_id = str(state.get('currentSeriesId') or '')
complete = bool(state.get('currentSeriesComplete'))

if latest_id == current_id:
    if latest_title and not state.get('currentSeriesTitle'):
        state['currentSeriesTitle'] = latest_title
    if latest_creator:
        state['spotifyCreator'] = latest_creator
        state['sourceChannel'] = latest_creator
    state['spotifyEpisodeUrl'] = f'https://open.spotify.com/episode/{latest_id}'
    STATE_PATH.write_text(json.dumps(state, indent=2) + '\n')
    print(f'Spotify source current: {latest_title or latest_id}')
    raise SystemExit(0)

if not complete:
    print(f'New Spotify episode {latest_id} is available, but current episode {current_id} is still being posted. Keeping continuity.')
    raise SystemExit(0)

state['currentSeriesId'] = latest_id
state['currentSeriesTitle'] = latest_title or f'Spotify episode {latest_id}'
state['currentSeriesEpisodeCount'] = 1
state['restartGeneration'] = int(state.get('restartGeneration') or 0) + 1
state['nextEpisode'] = 1
state['nextPart'] = 1
state['lastPostedPart'] = 0
state['lastPostedEpisodes'] = []
state['currentSeriesComplete'] = False
state['storyTotalParts'] = 1
state['sourceDurationSeconds'] = 0
state['spotifyEpisodeUrl'] = f'https://open.spotify.com/episode/{latest_id}'
if latest_creator:
    state['spotifyCreator'] = latest_creator
    state['sourceChannel'] = latest_creator
state['restartReason'] = 'Automatically advanced to the newest episode from the user-provided Spotify show.'
STATE_PATH.write_text(json.dumps(state, indent=2) + '\n')
print(f'Switched Rubaradaclips source to new Spotify episode: {state["currentSeriesTitle"]} ({latest_id})')
