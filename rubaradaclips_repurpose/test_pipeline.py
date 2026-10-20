"""Durable queue tests use fake APIs only; no media is published."""
import copy
import importlib.util
import json
import tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SPEC=importlib.util.spec_from_file_location('hisstory_pipeline',Path(__file__).with_name('pipeline.py'))
pipeline=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)

FIRST='8ffff3ff-ac10-4dee-8805-99b6979cdc63'
SECOND='66b15f7b-81f3-4bc3-ac84-c462f060025d'
THIRD='75f0a410-aaeb-4378-926c-1f490d0f3025'
POST_ID='6ad7c73f64a2e76528e29aed'
T0=datetime(2026,10,21,3,tzinfo=timezone.utc)


def state():
    return {'version':1,'feed':pipeline.FEED,'spotifyShowId':pipeline.SPOTIFY_SHOW_ID,
            'targetChannel':pipeline.TARGET_CHANNEL,
            'current':{'guid':SECOND,'title':"My Class Ate Our Teacher's Fertility Pills",'next_part':1},
            'completed':[FIRST],'last_post_at':'2026-10-20T19:58:12.484Z',
            'last_logical_post_key':'rubyclips:hisstory-370c2452f6b298c1:r16:p1',
            'last_buffer_post_id':'6ad7c73f64a2e76528e29aec','hold':False,'cadence_hours':6}


def release(part=1,total=1,verified=True):
    tag,key=pipeline.release_identity(SECOND,part)
    name=f'hisstory-{pipeline.series_id(SECOND)}-r16-part-{part:02d}.mp4'
    title="My Class Ate Our Teacher's Fertility Pills"
    caption=f'{title} — Part {part} of {total} #Fixture #rubaradaclips #storytime'
    manifest={'platform':'rubyclips-tiktok-story-v1','sourceProvider':'hisstory-spotify-rss',
              'sourceEpisodeGuid':SECOND,'spotifyShowId':pipeline.SPOTIFY_SHOW_ID,
              'targetChannel':pipeline.TARGET_CHANNEL,'spotifyEpisodeId':'0uaAgb3IbauXRNjvg1iesI',
              'segmentIndex':part,'segmentTotal':total,'sourceSeriesTitle':title,'file':name,
              'caption':caption,'logicalPostKey':key,'fullEpisodeVerified':verified,
              'sourceDurationSeconds':140.906,'segmentStartSeconds':0,'segmentEndSeconds':140.906}
    info={'guid':SECOND,'part':part,'totalParts':total,'releaseTag':tag,'logicalPostKey':key,
          'startSeconds':0,'endSeconds':140.906,'nextEpisode':{'guid':THIRD,'title':'Next story','next_part':1}}
    return {'manifest':manifest,'info':info,'receipt':None}


def pending(phase='accepted',part=1,total=1):
    source=release(part,total)
    manifest,info=source['manifest'],source['info']
    return {**info,'title':manifest['sourceSeriesTitle'],'file':manifest['file'],
            'caption':manifest['caption'],'videoUrl':pipeline.release_video_url(info['releaseTag'],manifest['file']),
            'sourceDurationSeconds':140.906,'phase':phase,'preparedAt':pipeline.iso(T0),
            'submittedAt':pipeline.iso(T0),'verifiedSource':True,
            **({'postId':POST_ID} if phase in ('accepted','sending','scheduled') else {})}


def post(current,status='sent',backfill=True):
    source=current['videoUrl']
    if backfill:
        source=(f'https://buffer-updates-media-backfill-bucket.s3.amazonaws.com/'
                f'{pipeline.BUFFER_ORG_ID}/{pipeline.TARGET_CHANNEL_ID}/{POST_ID}_video.mp4')
    return {'id':POST_ID,'channel':{'id':pipeline.TARGET_CHANNEL_ID},'text':current['caption'],
            'assets':[{'source':source}],'status':status,'error':None,
            'sentAt':pipeline.iso(T0),'externalLink':'https://tiktok.com/@rubaradaclips/video/7698841304393862414'}


class FakeIO:
    def __init__(self):
        self.events=[]
        self.saved=[]
        self.existing=None
        self.lookup_post=None
        self.lookup_error=None
        self.publish_error=None
        self.build_error=None
        self.built=release()
        self.create_count=0
        self.build_count=0
        self.receipt_error=None

    def save_state(self,value,reason):
        self.saved.append(copy.deepcopy(value))
        self.events.append(('save',(value.get('pending') or {}).get('phase'),reason))

    def find_release(self,tag):
        self.events.append(('find_release',tag))
        return self.existing

    def build(self,value):
        self.build_count+=1
        self.events.append(('build',))
        if self.build_error:
            raise self.build_error
        return self.built['manifest'],self.built['info']

    def ensure_release(self,manifest,info):
        self.events.append(('ensure_release',info['releaseTag']))
        return self.built,True

    def lookup(self,current):
        self.events.append(('lookup',current['releaseTag']))
        if self.lookup_error:
            raise self.lookup_error
        return {'ok':True,'videoUrl':current['videoUrl'],'post':copy.deepcopy(self.lookup_post)}

    def publish(self,current):
        self.events.append(('publish',current['releaseTag']))
        assert self.saved[-1]['pending']['phase']=='submitting'
        self.create_count+=1
        if self.publish_error:
            raise self.publish_error
        return {'ok':True,'postId':POST_ID,'channelName':pipeline.TARGET_CHANNEL,
                'channelId':pipeline.TARGET_CHANNEL_ID,'videoUrl':current['videoUrl']}

    def health(self):
        self.events.append(('health',))

    def write_receipt(self,current):
        self.events.append(('receipt',current['postId']))
        if self.receipt_error:
            raise self.receipt_error


class DurableQueueTests(unittest.TestCase):
    def queue(self,value=None):
        self.value=value or state()
        self.io=FakeIO()
        self.time=T0
        return pipeline.DurableQueue(self.value,self.io,lambda:self.time)

    def test_confirmed_backfill_advances_without_source(self):
        queue=self.queue()
        self.value['pending']=pending()
        self.io.lookup_post=post(self.value['pending'])
        self.io.build_error=pipeline.QueueError('Source is offline')
        result=queue.tick(prepare=True)
        self.assertEqual(result['status'],'sent')
        self.assertEqual(self.io.build_count,0)
        self.assertEqual(self.io.create_count,0)
        self.assertEqual(self.value['current']['guid'],THIRD)
        self.assertEqual(self.value['completed'],[FIRST,SECOND])
        self.assertIsNone(self.value['pending'])
        self.assertEqual(self.value['last_post_at'],pipeline.iso(T0))

    def test_recovery_precedes_cadence_and_hold(self):
        queue=self.queue()
        self.value['last_post_at']=pipeline.iso(T0-timedelta(minutes=20))
        self.value['hold']=True
        self.value['pending']=pending()
        self.io.lookup_post=post(self.value['pending'])
        self.assertEqual(queue.tick()['status'],'sent')
        self.assertEqual(self.io.build_count,0)

    def test_six_hours_from_actual_sent_time(self):
        queue=self.queue()
        self.time=pipeline.parse_time(self.value['last_post_at'])+timedelta(hours=5,minutes=59)
        self.assertEqual(queue.tick()['status'],'idle')
        self.time+=timedelta(minutes=1)
        self.assertEqual(queue.tick()['status'],'needs_prepare')
        self.assertEqual(self.value['current']['guid'],SECOND)
        self.assertEqual(self.value['completed'],[FIRST])

    def test_wrong_caption_account_and_backfill_are_blocked(self):
        mutations=[
            lambda p:p.update(text='Different story'),
            lambda p:p.update(channel={'id':'wrong'}),
            lambda p:p.update(assets=[{'source':p['assets'][0]['source'].replace(POST_ID,'0'*24)}]),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                queue=self.queue()
                self.value['pending']=pending()
                observed=post(self.value['pending'])
                mutate(observed)
                self.io.lookup_post=observed
                self.assertEqual(queue.tick()['status'],'blocked')
                self.assertEqual(self.value['current']['guid'],SECOND)
                self.assertEqual(self.io.create_count,0)

    def test_permanent_rejection_is_durable_and_never_auto_retried(self):
        queue=self.queue()
        self.value['pending']=pending()
        self.io.lookup_post=post(self.value['pending'],status='error')
        self.io.lookup_post['error']={'message':'TikTok moderation rejected this post'}
        self.assertEqual(queue.tick()['status'],'blocked')
        events=len(self.io.events)
        self.time+=timedelta(days=1)
        self.assertEqual(queue.tick(prepare=True)['status'],'blocked')
        self.assertEqual(len(self.io.events),events)
        self.assertEqual(self.io.create_count,0)
        self.assertIn('moderation',self.io.saved[-1]['pending']['failure']['reason'])

    def test_create_intent_and_id_are_saved_before_followup(self):
        queue=self.queue()
        result=queue.tick(prepare=True)
        self.assertEqual(result['status'],'pending')
        self.assertEqual(self.io.create_count,1)
        phases=[saved['pending']['phase'] for saved in self.io.saved]
        self.assertEqual(phases[:3],['prepared','submitting','accepted'])
        publish_index=next(i for i,event in enumerate(self.io.events) if event[0]=='publish')
        self.assertEqual(self.io.events[publish_index-1][0:2],('save','submitting'))
        self.assertEqual(self.io.saved[-1]['pending']['postId'],POST_ID)

    def test_lost_response_finds_sending_without_duplicate(self):
        queue=self.queue()
        self.value['pending']=pending(phase='submitting')
        self.io.lookup_post=post(self.value['pending'],status='sending')
        self.assertEqual(queue.tick()['status'],'pending')
        self.assertEqual(self.value['pending']['postId'],POST_ID)
        self.assertEqual(self.value['pending']['phase'],'sending')
        self.assertEqual(self.io.create_count,0)

    def test_unknown_requires_grace_and_two_separated_absent_lookups(self):
        queue=self.queue()
        self.value['pending']=pending(phase='submission_unknown')
        self.value['pending']['submittedAt']=pipeline.iso(T0-timedelta(minutes=16))
        self.assertEqual(queue.tick()['status'],'pending')
        self.assertEqual(self.io.create_count,0)
        self.time+=timedelta(seconds=30)
        queue.tick()
        self.assertEqual(self.value['pending']['absentLookups'],1)
        self.assertEqual(self.io.create_count,0)
        self.time+=timedelta(minutes=5)
        queue.tick()
        self.assertEqual(self.io.create_count,1)

    def test_known_post_id_is_never_recreated_if_temporarily_absent(self):
        queue=self.queue()
        self.value['pending']=pending()
        self.time+=timedelta(days=1)
        self.assertEqual(queue.tick(prepare=True)['status'],'pending')
        self.assertEqual(self.io.create_count,0)
        self.assertEqual(self.io.build_count,0)

    def test_existing_release_is_recovered_without_media_rebuild(self):
        queue=self.queue()
        self.io.existing=release(verified=False)
        self.io.existing['info']=None
        self.io.existing['receipt']={'ok':True,'postId':POST_ID,'channelName':pipeline.TARGET_CHANNEL}
        current=pending()
        self.io.lookup_post=post(current)
        self.assertEqual(queue.tick(prepare=True)['status'],'sent')
        self.assertEqual(self.io.build_count,0)
        self.assertEqual(self.io.create_count,0)
        self.assertEqual(self.value['completed'],[FIRST,SECOND])
        self.assertIsNone(self.value['current'])

    def test_source_failure_retains_exact_current_story(self):
        queue=self.queue()
        self.io.build_error=pipeline.QueueError('No verified source video is available')
        self.assertEqual(queue.tick(prepare=True)['status'],'source_blocked')
        self.assertEqual(self.value['completed'],[FIRST])
        self.assertEqual(self.value['current']['guid'],SECOND)
        self.assertEqual(self.value['current']['next_part'],1)
        self.assertEqual(self.io.create_count,0)
        self.assertIsNone(self.value.get('pending'))

    def test_receipt_failure_does_not_lose_accepted_post_identity(self):
        queue=self.queue()
        self.io.receipt_error=pipeline.QueueError('GitHub release temporarily unavailable')
        self.assertEqual(queue.tick(prepare=True)['status'],'pending')
        self.assertEqual(self.io.saved[-1]['pending']['postId'],POST_ID)
        self.io.lookup_post=post(self.value['pending'])
        self.assertEqual(queue.tick()['status'],'sent')
        self.assertEqual(self.io.create_count,1)

    def test_full_episode_end_and_tiny_tail_are_preserved(self):
        self.assertEqual(pipeline.segment_plan(168.874),[(0.0,168.874)])
        self.assertEqual(pipeline.segment_plan(360.05),[(0.0,180.0),(180.0,360.05)])
        self.assertEqual(pipeline.segment_plan(361),[(0.0,180.0),(180.0,360.0),(360.0,361.0)])
        for duration in (140.906,168.874,180,180.001,220,250,360.05,721.997):
            plan=pipeline.segment_plan(duration)
            self.assertEqual(plan[0][0],0)
            self.assertEqual(plan[-1][1],duration)
            self.assertAlmostEqual(sum(end-start for start,end in plan),duration)
            for index,part in enumerate(plan):
                if index:
                    self.assertEqual(part[0],plan[index-1][1])


class CatalogRefreshTests(unittest.TestCase):
    def test_new_rss_episode_refreshes_once_without_changing_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Path(directory)/'catalog.json'
            catalog.write_text(json.dumps({'episodes':[{'rssGuid':FIRST}]}))
            value=state()
            original=copy.deepcopy(value)
            def refresh(command,**kwargs):
                self.assertIn('refresh-catalog',command)
                catalog.write_text(json.dumps({'episodes':[{'rssGuid':FIRST},{'rssGuid':SECOND}]}))
                return SimpleNamespace(returncode=0)
            with patch.object(pipeline,'CATALOG_PATH',catalog),patch.object(pipeline.subprocess,'run',side_effect=refresh) as called:
                pipeline.ensure_catalog_guid(SECOND)
                pipeline.ensure_catalog_guid(SECOND)
                self.assertEqual(called.call_count,1)
            self.assertEqual(value,original)

    def test_missing_exact_mapping_after_refresh_stays_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog=Path(directory)/'catalog.json'
            catalog.write_text(json.dumps({'episodes':[{'rssGuid':FIRST}]}))
            with patch.object(pipeline,'CATALOG_PATH',catalog),patch.object(pipeline.subprocess,'run',return_value=SimpleNamespace(returncode=0)):
                with self.assertRaisesRegex(pipeline.QueueError,'no exact Spotify mapping'):
                    pipeline.ensure_catalog_guid(SECOND)


if __name__=='__main__':
    unittest.main()
