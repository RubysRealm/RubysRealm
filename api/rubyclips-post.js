// Rubarata uses the same Buffer video uploader as the working Takurada account.
import { createBufferVideoPost, getBufferTikTokChannel } from '../lib/buffer.js';
import {
  RUBARATA_CHANNEL_ID, RUBARATA_CHANNEL, SPOTIFY_SHOW_ID, PUBLISHER_VERSION,
  parseReleaseTag, validateSpotifyVideoManifest, validatePendingSource, postMatchesMedia
} from '../lib/rubarata-video.js';

const REPOSITORY = 'RubysRealm/RubysRealm';

async function bufferQuery(query, variables) {
  const key = process.env.BUFFER_API_KEY;
  if (!key) throw new Error('BUFFER_API_KEY is not configured.');
  const response = await fetch('https://api.buffer.com', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
    body: JSON.stringify({ query, variables }),
    signal: AbortSignal.timeout(25000)
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(`Buffer HTTP ${response.status}`);
    error.status = response.status;
    error.retryAfter = Number(response.headers.get('retry-after')) || 0;
    throw error;
  }
  if (data?.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
  return data?.data;
}

async function exactChannel() {
  const found = await getBufferTikTokChannel({ channelId: RUBARATA_CHANNEL_ID, channelName: RUBARATA_CHANNEL, allowDisabled: true });
  if (String(found?.channel?.id || '') !== RUBARATA_CHANNEL_ID ||
      ![found?.channel?.name, found?.channel?.displayName].some(name => String(name || '').replace(/^@/, '').toLowerCase() === RUBARATA_CHANNEL)) {
    throw new Error('Rubarata\'s exact connected TikTok account is unavailable.');
  }
  return found;
}

async function readQueue() {
  const response = await fetch(`https://raw.githubusercontent.com/${REPOSITORY}/main/rubaradaclips_repurpose/state.json?at=${Date.now()}`, {
    cache: 'no-store', signal: AbortSignal.timeout(15000)
  });
  if (!response.ok) throw new Error('The saved Rubarata queue is unavailable.');
  return response.json();
}

async function findExistingPost(videoUrl, manifest, tag) {
  const target = await exactChannel();
  const receiptResponse = await fetch(`https://github.com/${REPOSITORY}/releases/download/${encodeURIComponent(tag)}/publish.json`, {
    redirect: 'follow', cache: 'no-store', signal: AbortSignal.timeout(15000)
  });
  let postId = null;
  if (receiptResponse.ok) {
    const receipt = await receiptResponse.json();
    if (receipt.ok !== true || receipt.channelName !== RUBARATA_CHANNEL || receipt.videoUrl !== videoUrl ||
        receipt.logicalPostKey !== manifest.logicalPostKey || !/^[a-f0-9]{24}$/.test(receipt.postId || '')) {
      throw new Error('The saved Buffer receipt does not match this episode part.');
    }
    postId = receipt.postId;
  } else if (receiptResponse.status !== 404) {
    throw new Error(`The saved Buffer receipt could not be checked (${receiptResponse.status}).`);
  } else {
    const state = await readQueue();
    if (state.pending?.releaseTag === tag && state.pending?.logicalPostKey === manifest.logicalPostKey) postId = state.pending.postId || null;
  }
  if (postId) {
    const data = await bufferQuery(`query RubarataPost($id: PostId!) {
      post(input: { id: $id }) {
        id text status dueAt sentAt externalLink assets { source }
        channel { id name displayName service } error { message }
      }
    }`, { id: postId });
    if (data?.post?.id !== postId || !postMatchesMedia(data.post, manifest, videoUrl, target.organization.id)) {
      throw new Error('The saved Buffer post is missing or its account/media does not match; creation is paused.');
    }
    return data.post;
  }
  // Include sending/rejected posts. Never resubmit an ambiguous or rejected post.
  const data = await bufferQuery(`query RubarataPosts($organizationId: OrganizationId!, $channelId: ChannelId!) {
    posts(first: 60, input: {
      organizationId: $organizationId,
      filter: { channelIds: [$channelId] },
      sort: [{ field: createdAt, direction: desc }]
    }) { edges { node {
      id text status dueAt sentAt externalLink assets { source }
      channel { id name displayName service } error { message }
    } } }
  }`, { organizationId: target.organization.id, channelId: RUBARATA_CHANNEL_ID });
  // Buffer replaces source URLs with a post-specific media URL during processing.
  // A lost create response is recovered from the exact caption and verified
  // account/post media path. Multiple candidates always stop automatic creation.
  const matches = (data?.posts?.edges || []).map(edge => edge.node)
    .filter(post => postMatchesMedia(post, manifest, videoUrl, target.organization.id));
  if (matches.length > 1) throw new Error('Multiple existing posts match this episode part; automatic creation is paused for reconciliation.');
  return matches[0] || null;
}

async function readRelease(tag) {
  parseReleaseTag(tag);
  const base = `https://github.com/${REPOSITORY}/releases/download/${encodeURIComponent(tag)}`;
  const response = await fetch(`${base}/manifest.json`, { redirect: 'follow', cache: 'no-store', signal: AbortSignal.timeout(20000) });
  if (!response.ok) throw new Error(`Manifest unavailable (${response.status}).`);
  const manifest = await response.json();
  const numbering = validateSpotifyVideoManifest(manifest, tag, { forPublish: false });
  return { manifest, numbering, videoUrl: `${base}/${encodeURIComponent(manifest.file)}` };
}

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });
  if (String(req.query?.health || '') === '1') return res.status(200).json({
    ok: true, version: PUBLISHER_VERSION, channelName: RUBARATA_CHANNEL,
    spotifyShowId: SPOTIFY_SHOW_ID, originalVideoRequired: true,
    originalAudioRequired: true, confirmedSendRequired: true
  });
  try {
    const lookupTag = String(req.query?.lookupTag || '').trim();
    const tag = lookupTag || String(req.query?.tag || '').trim();
    if (!tag) return res.status(400).json({ ok: false, error: 'A current Spotify video release tag is required.' });
    const { manifest, numbering, videoUrl } = await readRelease(tag);
    const existing = await findExistingPost(videoUrl, manifest, tag);
    if (lookupTag) return res.status(200).json({ ok: true, post: existing, videoUrl, channelName: RUBARATA_CHANNEL });
    if (existing) return res.status(200).json({
      ok: true, postId: existing.id, post: existing, status: existing.status,
      deduplicated: true, channelId: RUBARATA_CHANNEL_ID, channelName: RUBARATA_CHANNEL,
      logicalPostKey: manifest.logicalPostKey, segmentIndex: numbering.index,
      segmentTotal: numbering.total, videoUrl, renderer: PUBLISHER_VERSION
    });

    validateSpotifyVideoManifest(manifest, tag);
    const state = await readQueue();
    validatePendingSource(state, manifest, tag);
    if (state.pending?.postId) throw new Error('An existing Buffer attempt must be reconciled before another submission.');
    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow', cache: 'no-store', signal: AbortSignal.timeout(15000) });
    if (!head.ok || Number(head.headers.get('content-length') || 0) < 10000) throw new Error('The verified MP4 is unavailable or incomplete.');
    const dueAt = new Date(Date.now() + 60000).toISOString();
    const post = await createBufferVideoPost({
      channelId: RUBARATA_CHANNEL_ID, caption: manifest.caption.trim(), videoUrl,
      dueAt, allowDisabled: true, dedupeVideoUrl: true, addTrendingHashtags: false
    });
    return res.status(200).json({
      ok: true, postId: post.id, status: post.status,
      deduplicated: post.deduplicated === true, dueAt,
      channelId: RUBARATA_CHANNEL_ID, channelName: RUBARATA_CHANNEL,
      sourceSeriesId: manifest.sourceSeriesId, spotifyShowId: SPOTIFY_SHOW_ID, caption: manifest.caption.trim(),
      logicalPostKey: manifest.logicalPostKey, segmentIndex: numbering.index,
      segmentTotal: numbering.total, videoUrl, renderer: PUBLISHER_VERSION
    });
  } catch (error) {
    const status = Number(error?.status) === 429 || String(error?.message || '').includes('Buffer HTTP 429') ? 429 : 503;
    const retryAfter = Number(error?.retryAfter) || 0;
    if (retryAfter > 0) res.setHeader('Retry-After', String(Math.ceil(retryAfter)));
    return res.status(status).json({ ok: false, error: String(error.message || error), retryAfter: retryAfter || null, version: PUBLISHER_VERSION });
  }
}
