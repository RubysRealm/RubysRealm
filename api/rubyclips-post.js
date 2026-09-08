import { createBufferVideoPost } from '../lib/buffer.js';

const RELEASE_OWNER = 'RubysRealm';
const RELEASE_REPO = 'RubysRealm';
const RUBYCLIPS_CHANNEL_ID = '6a9f6ff1cd8b9c702c2897e1';
const RUBYCLIPS_CHANNEL = 'rubaradaclips';

function validateManifest(m) {
  if (m?.platform !== 'rubyclips-facebook-repost-v1') throw new Error('Blocked: invalid RubyClips Facebook manifest.');
  if (m?.sourceOwnership !== 'user-provided-facebook-page') throw new Error('Blocked: source is not the user-provided Facebook page.');
  if (!/^\d+$/.test(String(m?.sourceVideoId || ''))) throw new Error('Blocked: missing source video id.');
  if (!m?.sourceUrl || !String(m.sourceUrl).includes('facebook.com')) throw new Error('Blocked: invalid Facebook source URL.');
  if (!m?.file || !String(m.file).endsWith('.mp4')) throw new Error('Blocked: missing MP4.');
  if (!String(m?.caption || '').trim()) throw new Error('Blocked: missing caption.');
  if (String(m?.targetChannel || '').replace(/^@/, '').toLowerCase() !== RUBYCLIPS_CHANNEL) {
    throw new Error('Blocked: wrong TikTok target.');
  }
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });

  try {
    const tag = String(req.query?.tag || '').trim();
    if (!/^rubyclips-fb-\d+(?:-s\d+)?$/.test(tag)) {
      return res.status(400).json({ ok: false, error: 'A valid RubyClips Facebook release tag is required.' });
    }

    const base = `https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
    const manifestResponse = await fetch(`${base}/manifest.json`, { redirect: 'follow', cache: 'no-store' });
    if (!manifestResponse.ok) throw new Error(`Manifest unavailable (${manifestResponse.status}).`);
    const manifest = await manifestResponse.json();
    validateManifest(manifest);

    const videoUrl = `${base}/${encodeURIComponent(manifest.file)}`;
    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow', cache: 'no-store' });
    if (!head.ok) throw new Error(`MP4 unavailable (${head.status}).`);

    const caption = String(manifest.caption).trim().slice(0, 2200);
    const dueAt = new Date(Date.now() + 45 * 1000).toISOString();

    // Deliberately skip Buffer account/channel discovery and recent-post listing here.
    // The RubyClips channel ID is pinned and the GitHub workflow/state provides dedupe.
    // This reduces each publish attempt to a single Buffer API mutation.
    const post = await createBufferVideoPost({
      channelId: RUBYCLIPS_CHANNEL_ID,
      caption,
      videoUrl,
      dueAt,
      allowDisabled: true
    });

    return res.status(200).json({
      ok: true,
      postId: post.id,
      status: post.status,
      dueAt,
      caption,
      channelId: RUBYCLIPS_CHANNEL_ID,
      channelName: RUBYCLIPS_CHANNEL,
      sourceVideoId: String(manifest.sourceVideoId),
      segmentIndex: Number(manifest.segmentIndex || 1),
      segmentTotal: Number(manifest.segmentTotal || 1),
      videoUrl,
      renderer: 'facebook-existing-video-low-request-v2'
    });
  } catch (error) {
    console.error('rubyclips-post failed', error);
    const status = String(error?.message || '').includes('Buffer HTTP 429') ? 429 : 500;
    return res.status(status).json({ ok: false, error: error.message });
  }
}
