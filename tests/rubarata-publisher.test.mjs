import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { validateSpotifyVideoManifest, validatePendingSource, SPOTIFY_SHOW_ID, SPOTIFY_FEED, postMatchesMedia } from '../lib/rubarata-video.js';
import handler from '../api/rubyclips-post.js';

const episode = '0svGSBB9AwLrvBJTLiufbc';
const guid = '8ffff3ff-ac10-4dee-8805-99b6979cdc63';
const series = 'hisstory-370c2452f6b298c1';
const tag = `rubyclips-tt-${series}-r16-p1`;
const fixture = () => ({
  platform: 'rubyclips-tiktok-story-v1', sourceProvider: 'hisstory-spotify-rss',
  spotifyShowId: SPOTIFY_SHOW_ID, targetChannel: 'rubaradaclips',
  sourceSeriesId: series, sourceEpisodeGuid: guid, spotifyEpisodeId: episode, restartGeneration: 16,
  logicalPostKey: `rubyclips:${series}:r16:p1`, segmentIndex: 1, segmentTotal: 1,
  sourceUrls: [SPOTIFY_FEED],
  sourceVideoVerified: true, sourceAudioVerified: true, fullEpisodeVerified: true,
  visualMode: 'original-source-video', sourceAccessMethod: 'spotify-native',
  sourceDurationSeconds: 168.874, segmentDurationSeconds: 168.875,
  sourceMedia: { fullEpisode: true, videoCodec: 'h264', audioCodec: 'aac', videoDurationSeconds: 168.866667, audioDurationSeconds: 168.87475 },
  segmentStartSeconds: 0, segmentEndSeconds: 168.874,
  mediaVideo: { durationSeconds: 168.866667 }, mediaAudio: { durationSeconds: 168.87475 },
  outputVideoCodec: 'h264', outputAudioCodec: 'aac', file: 'episode-part-01.mp4',
  caption: 'His Mom Made Him Kneel On Broken Glass | Part 1 of 1'
});

const completePublicFixture = () => {
  const id = '3XpQTdjxaKPEpHRKV5J8Ir';
  const rssGuid = '1fd9ad80-376a-48d4-a47b-b30d062c5b1b';
  const seriesId = 'hisstory-' + createHash('sha256').update(rssGuid).digest('hex').slice(0, 16);
  const visualUrl = 'https://smart-preview-clips.spotifycdn.com/previews/32b6d7f01eba11f1a1520b994db71638/0/32b6d7f01eba11f1a1520b994db71638.mp4';
  const manifest = {
    ...fixture(), sourceAccessMethod: 'spotify-complete-public-video',
    sourceSeriesId: seriesId, sourceEpisodeGuid: rssGuid, spotifyEpisodeId: id,
    logicalPostKey: `rubyclips:${seriesId}:r16:p1`,
    sourceDurationSeconds: 56.917, segmentDurationSeconds: 56.9175, segmentEndSeconds: 56.917,
    sourceMedia: { fullEpisode: true, videoCodec: 'h264', audioCodec: 'aac', videoDurationSeconds: 56.9, audioDurationSeconds: 56.9175 },
    mediaVideo: { durationSeconds: 56.9 }, mediaAudio: { durationSeconds: 56.9175 },
    caption: "My Neighbor's Husband Broke Down My Door | Part 1 of 1",
    transportUrl: visualUrl, transportAudioUsed: false,
    sourceVerification: {
      spotifyEpisodeId: id, showId: SPOTIFY_SHOW_ID, rssGuid, rssFeedUrl: SPOTIFY_FEED,
      sourceAccessMethod: 'spotify-complete-public-video', fullCoverage: true, fullNativeVideoVerified: true,
      nativeEpisodeId: id, nativeEmbedUrl: `https://open.spotify.com/embed/episode/${id}`,
      visualUrl, audioUrl: 'https://anchor.fm/s/10ff75318/podcast/play/116923624/source.mp3',
      nativeVideoStartSeconds: 0, nativeAudioStartSeconds: 0,
      nativeVideoDurationSeconds: 56.9, nativeAudioDurationSeconds: 56.917,
      fullAudioCorrelation: 0.999730, audioCorrelation: 0.997329,
      audioWindowCorrelations: [0.998, 0.999, 0.997329], audioOffsetsSeconds: [0, 0, 0],
      audioVerifiedDurationSeconds: 56.9175,
      visualSha256: 'a'.repeat(64), audioSha256: 'b'.repeat(64)
    }
  };
  return { manifest, releaseTag: `rubyclips-tt-${seriesId}-r16-p1` };
};

test('accepts a complete verified original episode with normal codec padding', () => {
  assert.deepEqual(validateSpotifyVideoManifest(fixture(), tag), { seriesId: series, index: 1, total: 1 });
});

test('blocks the actual old artwork pipeline and stale sources', () => {
  for (const patch of [
    { sourceProvider: 'snook-podcast-rss' },
    { spotifyShowId: '2lxmtcbizlC4eKhEa5HZ4I' },
    { visualMode: 'animated-audio-waveform-with-podcast-art' },
    { sourceVideoVerified: false }, { sourceAudioVerified: false },
    { fullEpisodeVerified: false }, { targetChannel: 'takurada' },
    { sourceAccessMethod: 'spotify-preview' }
  ]) assert.throws(() => validateSpotifyVideoManifest({ ...fixture(), ...patch }, tag), /Blocked:/);
});

test('rejects a cut-off ending and mismatched episode identity', () => {
  assert.throws(() => validateSpotifyVideoManifest({ ...fixture(), segmentEndSeconds: 160, segmentDurationSeconds: 160 }, tag), /story ending/);
  assert.throws(() => validateSpotifyVideoManifest({ ...fixture(), sourceSeriesId: '0uaAgb3IbauXRNjvg1iesI' }, tag), /episode and release/);
  assert.throws(() => validateSpotifyVideoManifest({ ...fixture(), file: '../other.mp4' }, tag), /filename/);
});

test('requires actual matching evidence for the creator video copy', () => {
  const visualUrl = 'https://www.facebook.com/HisYTStory/videos/his-mom-made-him-kneel-on-broken-glass/1237986135113831/';
  const paired = { ...fixture(), sourceAccessMethod: 'verified-creator-transport', transportUrl: visualUrl, transportAudioUsed: false, sourceVerification: {
    spotifyEpisodeId: episode, fullCoverage: true,
    visualUrl,
    audioUrl: 'https://anchor.fm/s/10ff75318/podcast/play/116612575/source.mp3',
    audioCorrelation: 0.9989, audioVerifiedDurationSeconds: 168.87475, previewFrameVerified: true
  } };
  validateSpotifyVideoManifest(paired, tag);
  assert.throws(() => validateSpotifyVideoManifest({ ...paired, sourceVerification: { ...paired.sourceVerification, audioCorrelation: 0.3 } }, tag), /audio identity/);
  assert.throws(() => validateSpotifyVideoManifest({ ...paired, sourceVerification: { ...paired.sourceVerification, previewFrameVerified: false } }, tag), /visuals/);
  assert.throws(() => validateSpotifyVideoManifest({ ...paired, sourceAccessMethod: 'verified-public-copy', sourceVerification: { ...paired.sourceVerification, previewFrameVerified: false } }, tag), /visuals/);
});

test('accepts a complete short episode directly from its Spotify CDN without claiming preview frame comparison', () => {
  const { manifest, releaseTag } = completePublicFixture();
  assert.equal(manifest.sourceVerification.previewFrameVerified, undefined);
  assert.equal(validateSpotifyVideoManifest(manifest, releaseTag).index, 1);
});

test('a 60-second public excerpt cannot stand in for a longer Spotify episode', () => {
  const { manifest, releaseTag } = completePublicFixture();
  for (const duration of [60.1, 168.874]) {
    const excerpt = { ...manifest, sourceDurationSeconds: duration, segmentEndSeconds: duration, segmentDurationSeconds: duration,
      sourceMedia: { ...manifest.sourceMedia, videoDurationSeconds: duration, audioDurationSeconds: duration },
      mediaVideo: { durationSeconds: duration }, mediaAudio: { durationSeconds: duration },
      sourceVerification: { ...manifest.sourceVerification, nativeVideoDurationSeconds: 60, nativeAudioDurationSeconds: 60, audioVerifiedDurationSeconds: duration }
    };
    assert.throws(() => validateSpotifyVideoManifest(excerpt, releaseTag), /at most 60 seconds/);
  }
  assert.throws(() => validateSpotifyVideoManifest({ ...manifest, sourceVerification: { ...manifest.sourceVerification, nativeVideoDurationSeconds: 40 } }, releaseTag), /complete Spotify episode/);
});

test('complete public Spotify video must bind the episode, show, RSS item, and exact embed', () => {
  const { manifest, releaseTag } = completePublicFixture();
  for (const proofPatch of [
    { spotifyEpisodeId: episode }, { nativeEpisodeId: episode }, { showId: '2lxmtcbizlC4eKhEa5HZ4I' },
    { rssGuid: guid }, { rssFeedUrl: 'https://anchor.fm/s/different/podcast/rss' },
    { nativeEmbedUrl: `https://open.spotify.com/embed/episode/${episode}` },
    { sourceAccessMethod: 'spotify-native' }, { fullCoverage: false }, { fullNativeVideoVerified: false }
  ]) assert.throws(() => validateSpotifyVideoManifest({ ...manifest, sourceVerification: { ...manifest.sourceVerification, ...proofPatch } }, releaseTag), /Blocked:/);
});

test('complete public video rejects spoofed Spotify hosts, unsupported paths, credentials, and transport substitutions', () => {
  const { manifest, releaseTag } = completePublicFixture();
  const original = manifest.transportUrl;
  for (const visualUrl of [
    original.replace('https:', 'http:'), original.replace('spotifycdn.com/', 'spotifycdn.com.evil.example/'),
    original.replace('smart-preview-clips.spotifycdn.com', 'other.spotifycdn.com'),
    original.replace('https://', 'https://user:secret@'), original.replace('.com/', '.com:444/'),
    original.replace('/0/', '/1/'), original.replace(/\.mp4$/, 'a.mp4'), original + '?different=1'
  ]) assert.throws(() => validateSpotifyVideoManifest({ ...manifest, transportUrl: visualUrl, sourceVerification: { ...manifest.sourceVerification, visualUrl } }, releaseTag), /Spotify CDN/);
  assert.throws(() => validateSpotifyVideoManifest({ ...manifest, transportUrl: original + '?other' }, releaseTag), /URL must agree/);
  assert.throws(() => validateSpotifyVideoManifest({ ...manifest, transportAudioUsed: true }, releaseTag), /RSS sound/);
  assert.throws(() => validateSpotifyVideoManifest({ ...manifest, sourceVerification: { ...manifest.sourceVerification, audioUrl: 'https://anchor.fm.evil.example/s/10ff75318/podcast/play/123/audio.mp3' } }, releaseTag), /official RSS sound/);
});

test('complete public video requires measured whole soundtrack identity and timing', () => {
  const { manifest, releaseTag } = completePublicFixture();
  for (const proofPatch of [
    { audioCorrelation: 0.94 }, { fullAudioCorrelation: 0.94 },
    { audioWindowCorrelations: [0.99, 0.6, 0.99] }, { audioWindowCorrelations: [0.99] },
    { audioOffsetsSeconds: [0, 0.126, 0] }, { audioOffsetsSeconds: [0, Number.NaN, 0] },
    { audioVerifiedDurationSeconds: 40 }, { visualSha256: '' }, { audioSha256: '' }
  ]) assert.throws(() => validateSpotifyVideoManifest({ ...manifest, sourceVerification: { ...manifest.sourceVerification, ...proofPatch } }, releaseTag), /Blocked:/);
});

test('both complete native streams must start at zero and retain the ending', () => {
  const { manifest, releaseTag } = completePublicFixture();
  for (const proofPatch of [
    { nativeVideoStartSeconds: 0.002 }, { nativeAudioStartSeconds: -0.002 },
    { nativeVideoStartSeconds: undefined }, { nativeAudioStartSeconds: Number.NaN },
    { nativeAudioDurationSeconds: 56.5 }, { nativeVideoDurationSeconds: 57.3 }
  ]) assert.throws(() => validateSpotifyVideoManifest({ ...manifest, sourceVerification: { ...manifest.sourceVerification, ...proofPatch } }, releaseTag), /native public video streams/);
});

test('only the next durably saved pending part can be created', () => {
  const m = fixture();
  const state = { spotifyShowId: SPOTIFY_SHOW_ID, targetChannel: 'rubaradaclips', current: { guid, next_part: 1 },
    pending: { releaseTag: tag, logicalPostKey: m.logicalPostKey } };
  validatePendingSource(state, m, tag);
  assert.throws(() => validatePendingSource({ ...state, current: { guid, next_part: 2 } }, m, tag), /next item/);
  assert.throws(() => validatePendingSource({ ...state, pending: null }, m, tag), /saved before/);
  assert.throws(() => validatePendingSource({ ...state, blocked: { reason: 'TikTok rejected' } }, m, tag), /attention/);
  assert.throws(() => validatePendingSource({ ...state, last_post_at: new Date().toISOString() }, m, tag), /six hours/);
});

test('lookup recovers a sending post without making any create request', async () => {
  const oldFetch = globalThis.fetch;
  const oldKey = process.env.BUFFER_API_KEY;
  process.env.BUFFER_API_KEY = 'test-fixture-not-a-real-key';
  const videoUrl = `https://github.com/RubysRealm/RubysRealm/releases/download/${tag}/episode-part-01.mp4`;
  const postId = '6ad7c73f64a2e76528e29aec';
  const org = '6a909de43dfa01f80e2d23c6';
  const requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url: String(url), body: options.body });
    if (String(url).endsWith('/manifest.json')) return Response.json(fixture());
    if (String(url).endsWith('/publish.json')) return new Response('', { status: 404 });
    if (String(url).includes('/state.json?')) return Response.json({ pending: { releaseTag: tag, logicalPostKey: fixture().logicalPostKey } });
    const query = JSON.parse(options.body || '{}').query || '';
    assert.ok(!query.includes('mutation'), 'Read-only recovery must not submit a post');
    if (query.includes('organizations')) return Response.json({ data: { account: { organizations: [{ id: org }] } } });
    if (query.includes('GetChannels')) return Response.json({ data: { channels: [{ id: '6a9f6ff1cd8b9c702c2897e1', name: 'rubaradaclips', displayName: 'rubaradaclips', service: 'tiktok' }] } });
    assert.ok(query.includes('RubarataPosts'));
    assert.ok(!query.includes('status: ['), 'Sending and rejected states must remain visible');
    return Response.json({ data: { posts: { edges: [{ node: { id: postId, text: fixture().caption, status: 'sending', assets: [{ source: `https://buffer-updates-media-backfill-bucket.s3.amazonaws.com/${org}/6a9f6ff1cd8b9c702c2897e1/${postId}_video.mp4` }], channel: { id: '6a9f6ff1cd8b9c702c2897e1' } } }] } } });
  };
  const res = { code: null, body: null, setHeader() {}, status(code) { this.code = code; return this; }, json(body) { this.body = body; return this; } };
  try {
    await handler({ method: 'GET', query: { lookupTag: tag } }, res);
    assert.equal(res.code, 200);
    assert.equal(res.body.post.status, 'sending');
    assert.equal(res.body.post.id, postId);
    assert.ok(requests.length > 1);
  } finally {
    globalThis.fetch = oldFetch;
    if (oldKey === undefined) delete process.env.BUFFER_API_KEY; else process.env.BUFFER_API_KEY = oldKey;
  }
});

test('Buffer rewritten media must match the exact account and post ID', () => {
  const m = fixture();
  const id = '6ad7c73f64a2e76528e29aec';
  const org = '6a909de43dfa01f80e2d23c6';
  const channel = '6a9f6ff1cd8b9c702c2897e1';
  const asset = `https://buffer-updates-media-backfill-bucket.s3.amazonaws.com/${org}/${channel}/${id}_video.mp4`;
  const post = { id, text: m.caption, channel: { id: channel }, assets: [{ source: asset }] };
  assert.equal(postMatchesMedia(post, m, 'https://original/video.mp4', org), true);
  assert.equal(postMatchesMedia({ ...post, id: '6ad71f8b8c1133338d53df60' }, m, 'https://original/video.mp4', org), false);
  assert.equal(postMatchesMedia({ ...post, channel: { id: '6a909fedccaf649a672c1347' } }, m, 'https://original/video.mp4', org), false);
  assert.equal(postMatchesMedia({ ...post, assets: [{ source: asset + '?different=1' }] }, m, 'https://original/video.mp4', org), false);
});

test('a legacy measured-short v16 receipt is read-only and cannot publish again', () => {
  const old = { ...fixture(), segmentDurationSeconds: 168 };
  delete old.sourceVideoVerified;
  assert.equal(validateSpotifyVideoManifest(old, tag, { forPublish: false }).index, 1);
  assert.throws(() => validateSpotifyVideoManifest(old, tag), /full-episode video and audio/);
  assert.throws(() => validateSpotifyVideoManifest({ ...fixture(), segmentDurationSeconds: 168, segmentEndSeconds: 168 }, tag), /story ending/);
  assert.throws(() => validateSpotifyVideoManifest({ ...fixture(), sourceDurationSeconds: 168, segmentDurationSeconds: 168, segmentEndSeconds: 168 }, tag), /measured full original media/);
});
