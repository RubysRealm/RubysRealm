import { createBufferVideoPost } from '../lib/buffer.js';

const RELEASE_OWNER = 'RubysRealm';
const RELEASE_REPO = 'RubysRealm';
const RUBYCLIPS_CHANNEL_ID = '6a9f6ff1cd8b9c702c2897e1';
const RUBYCLIPS_CHANNEL = 'rubaradaclips';
const FACEBOOK_PRESET_PLATFORM = 'rubyclips-facebook-existing-v2';

function validateManifest(m) {
  if (m?.platform !== FACEBOOK_PRESET_PLATFORM) throw new Error('Blocked: invalid RubyClips Facebook preset-part manifest.');
  if (m?.sourceOwnership !== 'user-provided-facebook-page') throw new Error('Blocked: source is not the user-provided Facebook page.');
  if (m?.presetPartPreserved !== true || m?.technicalSplitOnly !== false) throw new Error('Blocked: Facebook preset part was modified or split.');
  if (m?.titleBurnedIn !== false || m?.partLabelBurnedIn !== false) throw new Error('Blocked: preset Facebook part contains generated overlays.');
  if (Number(m?.segmentIndex || 0) !== 1 || Number(m?.segmentTotal || 0) !== 1) throw new Error('Blocked: preset Facebook part segmentation is not allowed.');
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
    if (!/^rubyclips-fb-\d+$/.test(tag)) {
      return res.status(400).json({ ok: false, error: 'A valid RubyClips Facebook preset-part release tag is required.' });
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

    // The target is pinned to the user's RubyClips TikTok channel. Generic
    // generated RubyClips publishing remains disabled elsewhere.
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
      segmentIndex: 1,
      segmentTotal: 1,
      videoUrl,
      renderer: 'facebook-existing-preset-part-v3'
    });
  } catch (error) {
    console.error('rubyclips-post failed', error);
    const status = String(error?.message || '').includes('Buffer HTTP 429') ? 429 : 500;
    return res.status(status).json({ ok: false, error: error.message });
  }
}
