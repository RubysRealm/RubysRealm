"""Continuity tests: simulated media/Buffer only; never publish real posts."""
import copy
import unittest
from datetime import timedelta
from test_pipeline import pipeline, T0


EPISODES = [
    {'guid': 'test-story-a', 'title': 'Test story A', 'duration': 421.125},
    {'guid': 'test-story-b', 'title': 'Test story B', 'duration': 115.008},
    {'guid': 'test-story-c', 'title': 'Test story C', 'duration': 721.997},
]


class MemoryIO:
    def __init__(self, clock):
        self.clock = clock
        self.saved = None
        self.releases = {}
        self.posts = {}
        self.create_count = 0
        self.build_error = False

    def save_state(self, value, reason):
        self.saved = copy.deepcopy(value)

    def find_release(self, tag):
        return copy.deepcopy(self.releases.get(tag))

    def build(self, state):
        if self.build_error:
            raise pipeline.QueueError('Temporary source outage in simulated test')
        ep, part = pipeline.selected(state, EPISODES)
        if ep is None:
            return None
        segments = pipeline.segment_plan(ep['duration'])
        state['current'] = {'guid': ep['guid'], 'title': ep['title'], 'next_part': part,
                            'sourceDurationSeconds': ep['duration'], 'segments': segments}
        tag, key = pipeline.release_identity(ep['guid'], part)
        start, end = segments[part - 1]
        manifest = {'sourceEpisodeGuid': ep['guid'], 'sourceSeriesTitle': ep['title'],
                    'spotifyShowId': pipeline.SPOTIFY_SHOW_ID,
                    'targetChannel': pipeline.TARGET_CHANNEL,
                    'segmentIndex': part, 'segmentTotal': len(segments),
                    'logicalPostKey': key, 'fullEpisodeVerified': True,
                    'file': f'test-part-{part}.mp4',
                    'caption': f"{ep['title']} - Part {part} of {len(segments)}",
                    'sourceDurationSeconds': ep['duration'],
                    'segmentStartSeconds': start, 'segmentEndSeconds': end}
        done = set(state['completed']) | {ep['guid']}
        following = next((row for row in EPISODES if row['guid'] not in done), None)
        info = {'guid': ep['guid'], 'part': part, 'totalParts': len(segments),
                'logicalPostKey': key, 'releaseTag': tag, 'startSeconds': start, 'endSeconds': end,
                'nextEpisode': ({'guid': following['guid'], 'title': following['title'], 'next_part': 1}
                                if following else None)}
        return manifest, info

    def ensure_release(self, manifest, info):
        tag = info['releaseTag']
        if tag in self.releases:
            return copy.deepcopy(self.releases[tag]), False
        release = {'manifest': copy.deepcopy(manifest), 'info': copy.deepcopy(info), 'receipt': None}
        self.releases[tag] = release
        return copy.deepcopy(release), True

    def lookup(self, pending):
        return {'ok': True, 'videoUrl': pending['videoUrl'],
                'post': copy.deepcopy(self.posts.get(pending['releaseTag']))}

    def publish(self, pending):
        assert self.saved['pending']['phase'] == 'submitting'
        assert pending['releaseTag'] not in self.posts, 'Duplicate simulated post'
        self.create_count += 1
        post_id = f'{self.create_count:024x}'
        self.posts[pending['releaseTag']] = {
            'id': post_id, 'channel': {'id': pipeline.TARGET_CHANNEL_ID},
            'text': pending['caption'], 'assets': [{'source': pending['videoUrl']}],
            'status': 'sending', 'error': None, 'sentAt': None, 'externalLink': None}
        return {'ok': True, 'postId': post_id, 'channelName': pipeline.TARGET_CHANNEL,
                'channelId': pipeline.TARGET_CHANNEL_ID, 'videoUrl': pending['videoUrl']}

    def health(self):
        pass

    def write_receipt(self, pending):
        pass


class ContinuousProgressionTests(unittest.TestCase):
    def setUp(self):
        self.clock = [T0]
        self.io = MemoryIO(lambda: self.clock[0])
        self.io.saved = {'version': 1, 'feed': pipeline.FEED,
                         'spotifyShowId': pipeline.SPOTIFY_SHOW_ID,
                         'targetChannel': pipeline.TARGET_CHANNEL,
                         'current': None, 'completed': [], 'hold': False,
                         'last_post_at': pipeline.iso(T0 - timedelta(hours=6)),
                         'cadence_hours': 6}

    def restart(self):
        return pipeline.DurableQueue(copy.deepcopy(self.io.saved), self.io, lambda: self.clock[0])

    def test_nine_parts_three_stories_with_restart_after_every_step(self):
        expected = [(ep['guid'], part) for ep in EPISODES
                    for part in range(1, len(pipeline.segment_plan(ep['duration'])) + 1)]
        self.assertEqual(len(expected), 9)
        for number, (guid, part) in enumerate(expected, 1):
            with self.subTest(number=number, guid=guid, part=part):
                self.assertEqual(self.restart().tick(prepare=True)['status'], 'pending')
                saved = self.io.saved
                self.assertEqual((saved['current']['guid'], saved['current']['next_part']), (guid, part))
                tag = saved['pending']['releaseTag']
                self.assertEqual(self.restart().tick(prepare=True)['status'], 'pending')
                self.assertEqual(self.io.create_count, number)
                observed = self.io.posts[tag]
                observed.update(status='sent', sentAt=pipeline.iso(self.clock[0]),
                                externalLink=f'https://tiktok.com/@rubaradaclips/video/{7000000000000000000 + number}')
                self.assertEqual(self.restart().tick()['status'], 'sent')
                self.assertIsNone(self.io.saved['pending'])
                self.clock[0] += timedelta(hours=6, microseconds=-1)
                self.assertEqual(self.restart().tick(prepare=True)['status'], 'idle')
                self.assertEqual(self.io.create_count, number)
                self.clock[0] += timedelta(microseconds=1)
        self.assertEqual(self.io.saved['completed'], [ep['guid'] for ep in EPISODES])
        self.assertIsNone(self.io.saved['current'])
        self.assertEqual(self.restart().tick(prepare=True)['status'], 'idle')
        self.assertEqual(self.io.create_count, 9)

    def test_source_failure_retries_without_skipping_story_or_changing_cadence(self):
        self.io.build_error = True
        original = self.io.saved['last_post_at']
        self.assertEqual(self.restart().tick(prepare=True)['status'], 'source_blocked')
        self.assertEqual(self.io.saved['completed'], [])
        self.assertEqual(self.io.saved['last_post_at'], original)
        self.io.build_error = False
        self.assertEqual(self.restart().tick(prepare=True)['status'], 'pending')
        self.assertEqual(self.io.saved['current']['guid'], EPISODES[0]['guid'])
        self.assertEqual(self.io.saved['current']['next_part'], 1)
        self.assertEqual(self.io.create_count, 1)


if __name__ == '__main__':
    unittest.main()
