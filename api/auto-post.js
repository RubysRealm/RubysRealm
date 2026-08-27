import { contentBank } from '../content/content-bank.js';
import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

function isAuthorized(req) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) return req.headers.authorization === `Bearer ${cronSecret}`;
  return req.headers['x-vercel-cron'] === '1' || req.headers['x-vercel-cron'] === 'true';
}

function pickContent() {
  const epochDay = Math.floor(Date.now() / 86400000);
  return contentBank[epochDay % contentBank.length];
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });
  if (!isAuthorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  try {
    const target = await getBufferTikTokChannel();
    if (!target) return res.status(404).json({ error: 'No TikTok channel connected in Buffer.' });

    const item = pickContent();
    const origin = process.env.PUBLIC_BASE_URL || 'https://rubys-realm.vercel.app';
    const videoUrl = `${origin}/videos/${item.id}.mp4`;

    const post = await createBufferVideoPost({
      channelId: target.channel.id,
      caption: item.caption,
      videoUrl
    });

    return res.status(200).json({
      ok: true,
      content: { id: item.id, format: item.format, videoUrl },
      post
    });
  } catch (error) {
    console.error('auto-post failed', error);
    return res.status(500).json({ ok: false, error: error.message });
  }
}
