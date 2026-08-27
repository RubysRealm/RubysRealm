import { getBufferTikTokChannel } from '../lib/buffer.js';

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const found = await getBufferTikTokChannel();
    if (!found) {
      return res.status(404).json({ ok: false, connected: false, message: 'No TikTok channel found in Buffer.' });
    }

    return res.status(200).json({
      ok: true,
      connected: true,
      organization: { id: found.organization.id, name: found.organization.name },
      channel: { id: found.channel.id, name: found.channel.name, service: found.channel.service }
    });
  } catch (error) {
    return res.status(500).json({ ok: false, connected: false, message: error.message });
  }
}
