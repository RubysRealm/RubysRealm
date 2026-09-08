#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / 'promotion'
STATE_PATH = BASE / 'state.json'
RELEASES_PATH = BASE / 'releases.json'
WORK = BASE / 'work'
OUT = BASE / 'output'
PROMO_ENDPOINT = 'https://rubys-realm.vercel.app/api/promo-post'
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
COOLDOWN_SECONDS = 3 * 60 * 60
MAX_PER_RUN = 2


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def iso_to_ts(value):
    if not value:
        return 0
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except Exception:
        return 0


def source_pair(tag):
    if tag.startswith('rubyclips-fb-'):
        return 'rubaradaclips', 'takurada'
    if tag.startswith('podcast-part-') or tag.startswith('reference-story-'):
        return 'takurada', 'rubaradaclips'
    return None


def safe_tag(tag):
    return re.sub(r'[^A-Za-z0-9._-]+', '-', tag).strip('-')[:180]


def choose_releases(releases, state):
    promoted = {str(x) for x in state.get('promotedReleaseTags', [])}
    last_by_target = state.get('lastPromoAtByTarget') or {}
    now = time.time()
    candidates = []
    for release in releases:
        tag = str(release.get('tag_name') or '')
        pair = source_pair(tag)
        if not pair or tag in promoted:
            continue
        assets = release.get('assets') or []
        if not any(str(a.get('name') or '').lower().endswith('.mp4') for a in assets):
            continue
        if not any(str(a.get('name') or '') == 'manifest.json' for a in assets):
            continue
        source, target = pair
        last = iso_to_ts(last_by_target.get(target))
        if last and now - last < COOLDOWN_SECONDS:
            continue
        candidates.append((iso_to_ts(release.get('published_at') or release.get('created_at')), tag, source, target, release))

    candidates.sort(key=lambda x: (x[0], x[1]))
    chosen = []
    used_targets = set()
    for item in candidates:
        _, _, _, target, _ = item
        if target in used_targets:
            continue
        chosen.append(item)
        used_targets.add(target)
        if len(chosen) >= MAX_PER_RUN:
            break
    return chosen


def download_release(tag, dest):
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    run(['gh', 'release', 'download', tag, '--repo', os.environ['GITHUB_REPOSITORY'], '-p', '*.mp4', '-p', 'manifest.json', '-D', str(dest)])
    videos = sorted([p for p in dest.glob('*.mp4') if p.is_file()], key=lambda p: p.stat().st_size, reverse=True)
    manifest = dest / 'manifest.json'
    if not videos or not manifest.exists():
        raise RuntimeError(f'{tag}: source media or manifest missing')
    return videos[0], manifest


def probe_duration(path):
    p = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)], capture_output=True)
    return float(p.stdout.strip())


def title_from_manifest(m):
    values = [
        m.get('displayTitle'),
        m.get('seriesTitle'),
        m.get('title'),
        m.get('originalDescription'),
        m.get('originalTitle'),
        m.get('caption'),
    ]
    text = next((str(v).strip() for v in values if str(v or '').strip()), 'New video')
    text = re.sub(r'#[A-Za-z0-9_]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip(' -–—|')
    lines = textwrap.wrap(text, width=30, break_long_words=False, break_on_hyphens=False)[:2]
    if not lines:
        lines = ['New video']
    return '\n'.join(lines)


def part_from_manifest(m):
    if m.get('partLabel'):
        return str(m['partLabel'])
    if m.get('part'):
        return str(m['part'])
    if m.get('partNumber') and m.get('totalParts'):
        return f"Part {m['partNumber']}/{m['totalParts']}"
    if m.get('segmentIndex') and m.get('segmentTotal'):
        return f"Part {m['segmentIndex']}/{m['segmentTotal']}"
    return 'Watch the full video'


def build_teaser(source_video, source_manifest_path, source_channel, target_channel, out_dir, source_tag):
    m = json.loads(source_manifest_path.read_text())
    duration = probe_duration(source_video)
    if duration <= 0:
        raise RuntimeError('invalid source duration')
    teaser_len = min(15.0, max(6.0, duration))
    start = 0.0 if duration <= teaser_len + 1 else min(2.0, max(0.0, duration - teaser_len))

    title = title_from_manifest(m)
    part = part_from_manifest(m)
    source_label = f'FULL VIDEO ON @{source_channel}'

    out_dir.mkdir(parents=True, exist_ok=True)
    title_file = out_dir / 'title.txt'
    part_file = out_dir / 'part.txt'
    source_file = out_dir / 'source.txt'
    title_file.write_text(title, encoding='utf-8')
    part_file.write_text(part, encoding='utf-8')
    source_file.write_text(source_label, encoding='utf-8')

    def esc(path):
        return path.as_posix().replace(':', '\\:').replace("'", "\\'")

    vf = (
        'scale=1080:1920:force_original_aspect_ratio=decrease,'
        'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1,'
        f"drawtext=fontfile={FONT}:textfile='{esc(title_file)}':fontcolor=white:fontsize=48:line_spacing=8:box=1:boxcolor=black@0.72:boxborderw=18:x=(w-text_w)/2:y=h*0.045,"
        f"drawtext=fontfile={FONT}:textfile='{esc(part_file)}':fontcolor=white:fontsize=38:box=1:boxcolor=black@0.65:boxborderw=14:x=(w-text_w)/2:y=h*0.18,"
        f"drawtext=fontfile={FONT}:textfile='{esc(source_file)}':fontcolor=white:fontsize=42:box=1:boxcolor=black@0.76:boxborderw=16:x=(w-text_w)/2:y=h*0.86"
    )
    promo_name = f"promo-{safe_tag(source_tag)}.mp4"
    promo = out_dir / promo_name
    run([
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-ss', f'{start:.3f}', '-i', str(source_video), '-t', f'{teaser_len:.3f}',
        '-vf', vf, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '144k', '-ar', '48000', '-movflags', '+faststart', str(promo)
    ])
    produced = probe_duration(promo)
    if produced < 4 or produced > 30 or promo.stat().st_size < 150000:
        raise RuntimeError('promo teaser failed validation')

    caption = f"{title.replace(chr(10), ' ')} — {part}. Full video on @{source_channel}. #rubysrealm #storytime #watchmore"
    manifest = {
        'platform': 'rubysrealm-promo-teaser-v1',
        'ownedChannelsOnly': True,
        'artificialEngagement': False,
        'sourceReleaseTag': source_tag,
        'sourceChannel': source_channel,
        'targetChannel': target_channel,
        'title': title.replace('\n', ' '),
        'partLabel': part,
        'durationSeconds': round(produced, 3),
        'file': promo.name,
        'caption': caption[:2200],
    }
    manifest_path = out_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return promo, manifest_path, manifest


def publish_release(source_tag, promo, manifest_path):
    promo_tag = f'promo-{safe_tag(source_tag)}'
    repo = os.environ['GITHUB_REPOSITORY']
    exists = subprocess.run(['gh', 'release', 'view', promo_tag, '--repo', repo], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if exists:
        run(['gh', 'release', 'upload', promo_tag, str(promo), str(manifest_path), '--clobber', '--repo', repo])
    else:
        run([
            'gh', 'release', 'create', promo_tag, str(promo), str(manifest_path), '--repo', repo,
            '--title', f'Owned-channel promotion for {source_tag}',
            '--notes', 'Short teaser used only for legitimate cross-promotion between the user-owned TikTok channels.'
        ])
    return promo_tag


def call_publisher(promo_tag, expected_target):
    url = f'{PROMO_ENDPOINT}?tag={promo_tag}'
    last = None
    for attempt in range(8):
        try:
            with urlopen(url, timeout=90) as r:
                data = json.loads(r.read().decode())
            if not data.get('ok'):
                raise RuntimeError(json.dumps(data))
            actual = str(data.get('channelName') or '').lstrip('@').lower()
            if actual != expected_target:
                raise RuntimeError(f'wrong promotion target: {actual}')
            return data
        except (HTTPError, URLError, RuntimeError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(20 + attempt * 10)
    raise RuntimeError(f'promotion publish failed after retries: {last}')


def main():
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {'promotedReleaseTags': [], 'lastPromoAtByTarget': {}}
    releases = json.loads(RELEASES_PATH.read_text())
    chosen = choose_releases(releases, state)
    if not chosen:
        print('No eligible owned-channel video needs cross-promotion right now.')
        return

    promoted = [str(x) for x in state.get('promotedReleaseTags', [])]
    last_by_target = state.get('lastPromoAtByTarget') or {}
    results = []

    for _, tag, source, target, _release in chosen:
        item_work = WORK / safe_tag(tag)
        item_out = OUT / safe_tag(tag)
        source_video, source_manifest = download_release(tag, item_work)
        promo, manifest_path, manifest = build_teaser(source_video, source_manifest, source, target, item_out, tag)
        promo_tag = publish_release(tag, promo, manifest_path)
        response = call_publisher(promo_tag, target)
        if tag not in promoted:
            promoted.append(tag)
        last_by_target[target] = datetime.now(timezone.utc).isoformat()
        results.append({'sourceReleaseTag': tag, 'sourceChannel': source, 'targetChannel': target, 'promoTag': promo_tag, 'publisher': response})

    state['promotedReleaseTags'] = promoted
    state['lastPromoAtByTarget'] = last_by_target
    state['lastRunAt'] = datetime.now(timezone.utc).isoformat()
    state['lastResults'] = results
    STATE_PATH.write_text(json.dumps(state, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
