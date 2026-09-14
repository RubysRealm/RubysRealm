#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LEDGER = Path('tiktok_playlist_assignments.json')
ACCOUNT_ALIASES = {
    'master-pov': 'takurada',
    'takurada': 'takurada',
    'rubaradaclips': 'rubaradaclips',
}


def load(path: Path):
    if not path.exists():
        return {'version': 1, 'assignments': []}
    data = json.loads(path.read_text())
    data.setdefault('version', 1)
    data.setdefault('assignments', [])
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--account', required=True)
    ap.add_argument('--story-id', required=True)
    ap.add_argument('--story-title', required=True)
    ap.add_argument('--part', required=True, type=int)
    ap.add_argument('--total-parts', type=int)
    ap.add_argument('--post-id')
    ap.add_argument('--playlist-name')
    ap.add_argument('--source', default='workflow')
    ap.add_argument('--status', default='pending_tiktok_assignment')
    ap.add_argument('--ledger', default=str(DEFAULT_LEDGER))
    args = ap.parse_args()

    path = Path(args.ledger)
    data = load(path)
    playlist = (args.playlist_name or args.story_title).strip()
    account_raw = args.account.strip().lower()
    account = ACCOUNT_ALIASES.get(account_raw, account_raw)
    key = (account, str(args.story_id), int(args.part))
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    found = None
    for row in data['assignments']:
        row_account = ACCOUNT_ALIASES.get(str(row.get('account', '')).lower(), str(row.get('account', '')).lower())
        row_key = (row_account, str(row.get('storyId', '')), int(row.get('partNumber', 0)))
        if row_key == key:
            found = row
            break

    values = {
        'account': account,
        'storyId': str(args.story_id),
        'storyTitle': args.story_title.strip(),
        'playlistName': playlist,
        'partNumber': int(args.part),
        'totalParts': int(args.total_parts) if args.total_parts is not None else None,
        'bufferPostId': str(args.post_id) if args.post_id else None,
        'assignmentStatus': args.status,
        'source': args.source,
        'updatedAt': now,
    }
    if found is None:
        values['createdAt'] = now
        data['assignments'].append(values)
    else:
        created = found.get('createdAt') or now
        found.update(values)
        found['createdAt'] = created

    data['assignments'].sort(key=lambda r: (str(r.get('account','')), str(r.get('storyId','')), int(r.get('partNumber',0))))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(values, ensure_ascii=False))


if __name__ == '__main__':
    main()
