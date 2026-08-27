import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });
  try {
    const found = await getBufferTikTokChannel();
    if (!found) return res.status(404).json({ ok: false, error: 'No TikTok channel connected in Buffer.' });

    const post = await createBufferVideoPost({
      channelId: found.channel.id,
      caption: "That one second after work when you finally sit down… and your brain remembers EVERYTHING 😭 #relatable #afterwork #adulting #rubysrealm",
      videoUrl: "https://resource2.heygen.ai/aws_pacific/avatar_tmp/1592f1dded57439e808601ba8fbe8818/v19532a7a5136405597ae05ad88727b9f/caption_484da3cd2a0c4e56acc2b9aca12d6cef.mp4"
    });

    return res.status(200).json({ ok: true, post });
  } catch (error) {
    console.error(error);
    return res.status(500).json({ ok: false, error: error.message || 'Queue failed' });
  }
}
