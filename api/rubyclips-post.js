import { createBufferVideoPost } from '../lib/buffer.js';

const RELEASE_OWNER = 'RubysRealm';
const RELEASE_REPO = 'RubysRealm';
const RUBYCLIPS_CHANNEL_ID = '6a9f6ff1cd8b9c702c2897e1';
const RUBYCLIPS_CHANNEL = 'rubaradaclips';
const FACEBOOK_PLATFORM = 'rubyclips-facebook-repost-v1';
const MAX_AUTO_SECONDS = 599;
const PUBLISHER_VERSION = 'facebook-existing-video-parts-v5';

function validateManifest(m, tag) {
  if (m?.platform !== FACEBOOK_PLATFORM) throw new Error('Blocked: invalid RubyClips Facebook manifest.');
  if (m?.sourceOwnership !== 'user-provided-facebook-page') throw new Error('Blocked: source is not the user-provided Facebook page.');
  if (!/^\d+$/.test(String(m?.sourceVideoId || ''))) throw new Error('Blocked: missing source video id.');
  if (!m?.sourceUrl || !String(m.sourceUrl).includes('facebook.com')) throw new Error('Blocked: invalid Facebook source URL.');
  if (!m?.file || !String(m.file).endsWith('.mp4')) throw new Error('Blocked: missing MP4.');
  if (!String(m?.caption || '').trim()) throw new Error('Blocked: missing caption.');
  if (String(m?.targetChannel || '').replace(/^@/, '').toLowerCase() !== RUBYCLIPS_CHANNEL) throw new Error('Blocked: wrong TikTok target.');

  const index = Number(m?.segmentIndex || 0);
  const total = Number(m?.segmentTotal || 0);
  const segmentSeconds = Number(m?.segmentDurationSeconds || 0);
  const sourceSeconds = Number(m?.sourceDurationSeconds || 0);
  if (!Number.isInteger(index) || !Number.isInteger(total) || index < 1 || total < 1 || index > total) throw new Error('Blocked: invalid Facebook part numbering.');
  if (!(segmentSeconds > 0 && segmentSeconds <= MAX_AUTO_SECONDS)) throw new Error('Blocked: Facebook part is outside automatic TikTok duration limits.');

  if (total > 1) {
    if (!(sourceSeconds > MAX_AUTO_SECONDS) || m?.technicalSplitOnly !== true) throw new Error('Blocked: unverified Facebook split.');
    if (m?.titleBurnedIn !== true || m?.partLabelBurnedIn !== true) throw new Error('Blocked: multipart title/part layout is missing.');
    if (tag !== `rubyclips-fb-${m.sourceVideoId}-s${index}`) throw new Error('Blocked: release tag does not match Facebook part.');
  } else {
    if (m?.technicalSplitOnly === true) throw new Error('Blocked: unexpected Facebook split flag.');
    if (tag !== `rubyclips-fb-${m.sourceVideoId}`) throw new Error('Blocked: release tag does not match Facebook video.');
  }
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });

  if (String(req.query?.health || '') === '1') {
    return res.status(200).json({ ok: true, version: PUBLISHER_VERSION, channelName: RUBYCLIPS_CHANNEL });
  }

  try {
    const tag = String(req.query?.tag || '').trim();
    if (!/^rubyclips-fb-\d+(?:-s\d+)?$/.test(tag)) return res.status(400).json({ ok: false, error: 'A valid RubyClips Facebook release tag is required.' });

    const base = `https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
    const manifestResponse = await fetch(`${base}/manifest.json`, { redirect: 'follow', cache: 'no-store' });
    if (!manifestResponse.ok) throw new Error(`Manifest unavailable (${manifestResponse.status}).`);
    const manifest = await manifestResponse.json();
    validateManifest(manifest, tag);

    const videoUrl = `${base}/${encodeURIComponent(manifest.file)}`;
    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow', cache: 'no-store' });
    if (!head.ok) throw new Error(`MP4 unavailable (${head.status}).`);

    const caption = String(manifest.caption).trim().slice(0, 2200);
    const dueAt = new Date(Date.now() + 45 * 1000).toISOString();
    const post = await createBufferVideoPost({ channelId: RUBYCLIPS_CHANNEL_ID, caption, videoUrl, dueAt, allowDisabled: true });

    return res.status(200).json({
      ok: true,
      postId: post.id,
      status: post.status,
      dueAt,
      caption,
      channelId: RUBYCLIPS_CHANNEL_ID,
      channelName: RUBYCLIPS_CHANNEL,
      sourceVideoId: String(manifest.sourceVideoId),
      segmentIndex: Number(manifest.segmentIndex),
      segmentTotal: Number(manifest.segmentTotal),
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
