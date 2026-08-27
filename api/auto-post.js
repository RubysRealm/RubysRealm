import { contentBank } from '../content/content-bank.js';
import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const DAILY_POSTS = 6;
const SLOT_HOURS_UTC = [13, 16, 19, 22, 25, 28]; // 9am, noon, 3pm, 6pm, 9pm, midnight ET during EDT

function isAuthorized(req) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) return req.headers.authorization === `Bearer ${cronSecret}`;
  return req.headers['x-vercel-cron'] === '1' || req.headers['x-vercel-cron'] === 'true';
}

function scheduledSlots(now = new Date()) {
  const base = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0));
  let slots = SLOT_HOURS_UTC.map(hour => new Date(base.getTime() + hour * 3600000));

  while (slots.filter(d => d.getTime() > now.getTime() + 10 * 60000).length < DAILY_POSTS) {
    slots.push(new Date(slots[slots.length - 1].getTime() + 3 * 3600000));
  }

  return slots.filter(d => d.getTime() > now.getTime() + 10 * 60000).slice(0, DAILY_POSTS);
}

function contentForToday() {
  const epochDay = Math.floor(Date.now() / 86400000);
  const start = (epochDay * DAILY_POSTS) % contentBank.length;
  return Array.from({ length: DAILY_POSTS }, (_, i) => contentBank[(start + i) % contentBank.length]);
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });
  if (!isAuthorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  try {
    const target = await getBufferTikTokChannel();
    if (!target) return res.status(404).json({ error: 'No TikTok channel connected in Buffer.' });

    const origin = process.env.PUBLIC_BASE_URL || 'https://rubys-realm.vercel.app';
    const items = contentForToday();
    const slots = scheduledSlots();
    const created = [];

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      const videoUrl = `${origin}/api/video?id=${encodeURIComponent(item.id)}`;
      const dueAt = slots[i].toISOString();

      const post = await createBufferVideoPost({
        channelId: target.channel.id,
        caption: item.caption,
        videoUrl,
        dueAt
      });

      created.push({ contentId:item.id, format:item.format, videoUrl, dueAt, postId:post.id, status:post.status });
    }

    return res.status(200).json({
      ok:true,
      dailyPosts:DAILY_POSTS,
      channel:{ id:target.channel.id, name:target.channel.displayName || target.channel.name },
      created
    });
  } catch (error) {
    console.error('auto-post failed', error);
    return res.status(500).json({ ok:false, error:error.message });
  }
}
