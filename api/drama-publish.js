import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const OWNER = 'RubysRealm';
const REPO = 'RubysRealm';

function validTag(tag) {
  return /^original-drama-[A-Za-z0-9_-]+-ep[1-8]-[0-9]+$/.test(tag);
}

function validateManifest(m) {
  if (m?.platform !== 'original-short-drama-v1') throw new Error('Blocked: invalid drama manifest.');
  if (m?.originalOnly !== true) throw new Error('Blocked: drama is not marked original-only.');
  const ep = Number(m.episodeNumber);
  const total = Number(m.totalEpisodes);
  const duration = Number(m.durationSeconds);
  if (!Number.isInteger(ep) || ep < 1 || ep > 8) throw new Error('Blocked: invalid episode number.');
  if (total !== 8) throw new Error('Blocked: invalid season episode count.');
  if (!Number.isFinite(duration) || duration < 45 || duration > 100) throw new Error('Blocked: episode duration must be 45-100 seconds.');
  if (!m.seriesTitle || !m.episodeTitle || !m.cliffhanger) throw new Error('Blocked: missing series metadata.');
  if (!m.file || !String(m.file).endsWith('.mp4')) throw new Error('Blocked: invalid final media file.');
  if (m.rightsPolicy !== 'original-generated-assets-only') throw new Error('Blocked: rights policy missing.');
  if (m.qualityPassed !== true) throw new Error('Blocked: quality gate did not pass.');
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });
  try {
    const tag = String(req.query?.tag || '').trim();
    if (!validTag(tag)) return res.status(400).json({ ok: false, error: 'A valid original-drama release tag is required.' });

    const base = `https://github.com/${OWNER}/${REPO}/releases/download/${encodeURIComponent(tag)}`;
    const manifestResponse = await fetch(`${base}/manifest.json`, { redirect: 'follow', cache: 'no-store' });
    if (!manifestResponse.ok) throw new Error(`Drama manifest unavailable (${manifestResponse.status}).`);
    const manifest = await manifestResponse.json();
    validateManifest(manifest);

    const videoUrl = `${base}/${encodeURIComponent(manifest.file)}`;
    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow', cache: 'no-store' });
    if (!head.ok) throw new Error(`Drama MP4 unavailable (${head.status}).`);

    const target = await getBufferTikTokChannel();
    if (!target) throw new Error('No matching TikTok channel is connected in Buffer. Set BUFFER_TIKTOK_CHANNEL_ID or BUFFER_TIKTOK_CHANNEL_NAME for the drama account.');

    const caption = `${manifest.seriesTitle} — Episode ${manifest.episodeNumber}/${manifest.totalEpisodes}: ${manifest.episodeTitle} #shortdrama #dram series #storytok #originalseries`.replace('#dram series', '#dramaseries');
    const dueAt = new Date(Date.now() + 90 * 1000).toISOString();
    const post = await createBufferVideoPost({ channelId: target.channel.id, caption, videoUrl, dueAt });

    return res.status(200).json({
      ok: true,
      postId: post.id,
      status: post.status,
      dueAt,
      channelId: target.channel.id,
      channelName: target.channel.displayName || target.channel.name,
      seriesTitle: manifest.seriesTitle,
      episodeNumber: manifest.episodeNumber,
      videoUrl
    });
  } catch (error) {
    console.error('drama publish failed', error);
    return res.status(500).json({ ok: false, error: error.message });
  }
}
