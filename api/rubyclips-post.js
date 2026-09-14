import { createBufferVideoPost } from '../lib/buffer.js';

const RELEASE_OWNER = 'RubysRealm';
const RELEASE_REPO = 'RubysRealm';
const RUBYCLIPS_CHANNEL_ID = '6a9f6ff1cd8b9c702c2897e1';
const RUBYCLIPS_CHANNEL = 'rubaradaclips';
const FACEBOOK_PLATFORM = 'rubyclips-facebook-repost-v1';
const CREATOR_PLATFORM = 'rubyclips-creator-feed-v1';
const TIKTOK_STORY_PLATFORM = 'rubyclips-tiktok-story-v1';
const CREATOR_CHANNEL = '@bushcraftinthewildforest';
const TIKTOK_STORY_CHANNEL = '@muffindrama_us';
const MAX_AUTO_SECONDS = 599;
const MIN_STORY_RESTART_GENERATION = 2;
const REQUIRED_STORY_PIPELINE_REVISION = 'avsync-v3-idempotent';
const PUBLISHER_VERSION = 'existing-video-parts-v9-tiktok-idempotent';

function validateBase(m) {
  if (!m?.file || !String(m.file).endsWith('.mp4')) throw new Error('Blocked: missing MP4.');
  if (!String(m?.caption || '').trim()) throw new Error('Blocked: missing caption.');
  if (String(m?.targetChannel || '').replace(/^@/, '').toLowerCase() !== RUBYCLIPS_CHANNEL) throw new Error('Blocked: wrong TikTok target.');
  const segmentSeconds = Number(m?.segmentDurationSeconds || 0);
  if (!(segmentSeconds > 0 && segmentSeconds <= MAX_AUTO_SECONDS)) throw new Error('Blocked: part is outside automatic TikTok duration limits.');
  return segmentSeconds;
}

function validateLegacyCommon(m) {
  validateBase(m);
  const index = Number(m?.segmentIndex || 0);
  const total = Number(m?.segmentTotal || 0);
  const sourceSeconds = Number(m?.sourceDurationSeconds || 0);
  if (!Number.isInteger(index) || !Number.isInteger(total) || index < 1 || total < 1 || index > total) throw new Error('Blocked: invalid part numbering.');
  if (m?.titleBurnedIn !== true || m?.partLabelBurnedIn !== true) throw new Error('Blocked: title/part layout is missing.');
  if (total > 1 && (!(sourceSeconds > MAX_AUTO_SECONDS) || m?.technicalSplitOnly !== true)) throw new Error('Blocked: unverified multipart split.');
  if (total === 1 && m?.technicalSplitOnly === true) throw new Error('Blocked: unexpected split flag.');
  return { index, total };
}

function validateTikTokStory(m, tag) {
  validateBase(m);
  const index = Number(m?.segmentIndex || 0);
  if (!Number.isInteger(index) || index < 1) throw new Error('Blocked: invalid story part number.');
  if (String(m?.sourceProvider || '').toLowerCase() !== 'tiktok') throw new Error('Blocked: TikTok story provider mismatch.');
  if (String(m?.sourceChannel || '').toLowerCase() !== TIKTOK_STORY_CHANNEL.toLowerCase()) throw new Error('Blocked: TikTok story channel mismatch.');
  if (String(m?.pipelineRevision || '') !== REQUIRED_STORY_PIPELINE_REVISION) throw new Error('Blocked: stale TikTok story pipeline revision.');
  const seriesId = String(m?.sourceSeriesId || '').trim();
  if (!/^\d{10,25}$/.test(seriesId)) throw new Error('Blocked: invalid TikTok series id.');
  const restart = Number(m?.restartGeneration || 0);
  if (!Number.isInteger(restart) || restart < MIN_STORY_RESTART_GENERATION) throw new Error('Blocked: stale TikTok story generation.');
  const expectedLogicalPostKey = `rubyclips:${seriesId}:r${restart}:p${index}`;
  if (String(m?.logicalPostKey || '') !== expectedLogicalPostKey) throw new Error('Blocked: invalid logical post key.');
  const ids = Array.isArray(m?.sourceVideoIds) ? m.sourceVideoIds.map(x => String(x).trim()) : [];
  if (!ids.length || ids.some(id => !/^\d{10,25}$/.test(id))) throw new Error('Blocked: invalid TikTok episode ids.');
  const urls = Array.isArray(m?.sourceUrls) ? m.sourceUrls.map(String) : [];
  if (!urls.length || urls.some(url => !url.includes('tiktok.com/'))) throw new Error('Blocked: invalid TikTok episode URLs.');
  const storyHashtag = String(m?.storyHashtag || '').trim();
  if (!/^#[A-Za-z0-9]+$/.test(storyHashtag) || !String(m.caption).includes(storyHashtag)) throw new Error('Blocked: missing story-title hashtag.');
  const expected = `rubyclips-tt-${seriesId}-r${restart}-p${index}`;
  if (tag !== expected) throw new Error('Blocked: release tag does not match TikTok story restart/part.');
  return { index, total: Number(m?.segmentTotal || 0) || null };
}

function validateManifest(m, tag) {
  if (m?.platform === TIKTOK_STORY_PLATFORM) return validateTikTokStory(m, tag);

  const { index, total } = validateLegacyCommon(m);
  const id = String(m?.sourceVideoId || '').trim();

  if (m?.platform === FACEBOOK_PLATFORM) {
    if (m?.sourceOwnership !== 'user-provided-facebook-page') throw new Error('Blocked: source is not the configured Facebook page.');
    if (!/^\d+$/.test(id)) throw new Error('Blocked: missing Facebook video id.');
    if (!m?.sourceUrl || !String(m.sourceUrl).includes('facebook.com')) throw new Error('Blocked: invalid Facebook source URL.');
    const expected = total > 1 ? `rubyclips-fb-${id}-s${index}` : `rubyclips-fb-${id}`;
    if (tag !== expected) throw new Error('Blocked: release tag does not match Facebook part.');
    return { index, total };
  }

  if (m?.platform === CREATOR_PLATFORM) {
    if (String(m?.sourceProvider || '').toLowerCase() !== 'youtube') throw new Error('Blocked: creator fallback provider mismatch.');
    if (String(m?.sourceChannel || '').toLowerCase() !== CREATOR_CHANNEL.toLowerCase()) throw new Error('Blocked: creator fallback channel mismatch.');
    if (!/^[A-Za-z0-9_-]{6,20}$/.test(id)) throw new Error('Blocked: invalid creator source id.');
    const src = String(m?.sourceUrl || '');
    if (!(src.includes('youtube.com/') || src.includes('youtu.be/'))) throw new Error('Blocked: invalid creator source URL.');
    const expected = total > 1 ? `rubyclips-src-${id}-s${index}` : `rubyclips-src-${id}`;
    if (tag !== expected) throw new Error('Blocked: release tag does not match creator-feed part.');
    return { index, total };
  }

  throw new Error('Blocked: invalid RubyClips manifest platform.');
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });

  if (String(req.query?.health || '') === '1') {
    return res.status(200).json({ ok: true, version: PUBLISHER_VERSION, channelName: RUBYCLIPS_CHANNEL });
  }

  try {
    const tag = String(req.query?.tag || '').trim();
    if (!/^rubyclips-(?:fb-\d+|src-[A-Za-z0-9_-]{6,20})(?:-s\d+)?$/.test(tag) && !/^rubyclips-tt-\d{10,25}-r\d+-p\d+$/.test(tag)) {
      return res.status(400).json({ ok: false, error: 'A valid RubyClips release tag is required.' });
    }

    const base = `https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
    const manifestResponse = await fetch(`${base}/manifest.json`, { redirect: 'follow', cache: 'no-store' });
    if (!manifestResponse.ok) throw new Error(`Manifest unavailable (${manifestResponse.status}).`);
    const manifest = await manifestResponse.json();
    const numbering = validateManifest(manifest, tag);

    const videoUrl = `${base}/${encodeURIComponent(manifest.file)}`;
    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow', cache: 'no-store' });
    if (!head.ok) throw new Error(`MP4 unavailable (${head.status}).`);

    const caption = String(manifest.caption).trim().slice(0, 2200);
    const dueAt = new Date(Date.now() + 45 * 1000).toISOString();
    const post = await createBufferVideoPost({
      channelId: RUBYCLIPS_CHANNEL_ID,
      caption,
      videoUrl,
      dueAt,
      allowDisabled: true,
      dedupeVideoUrl: true
    });

    return res.status(200).json({
      ok: true,
      postId: post.id,
      status: post.status,
      deduplicated: post.deduplicated === true,
      dueAt,
      caption,
      channelId: RUBYCLIPS_CHANNEL_ID,
      channelName: RUBYCLIPS_CHANNEL,
      platform: manifest.platform,
      sourceVideoId: manifest.sourceVideoId ? String(manifest.sourceVideoId) : null,
      sourceSeriesId: manifest.sourceSeriesId ? String(manifest.sourceSeriesId) : null,
      sourceVideoIds: Array.isArray(manifest.sourceVideoIds) ? manifest.sourceVideoIds.map(String) : null,
      logicalPostKey: manifest.logicalPostKey || null,
      segmentIndex: numbering.index,
      segmentTotal: numbering.total,
      videoUrl,
      renderer: PUBLISHER_VERSION
    });
  } catch (error) {
    const status = Number(error?.status) === 429 || String(error?.message || '').includes('Buffer HTTP 429') ? 429 : 500;
    const retryAfter = Number(error?.retryAfter) || 0;
    if (status === 429 && retryAfter > 0) res.setHeader('Retry-After', String(Math.ceil(retryAfter)));
    console.error('rubyclips-post failed', error);
    return res.status(status).json({ ok: false, error: error.message, retryAfter: retryAfter || null, version: PUBLISHER_VERSION });
  }
}
