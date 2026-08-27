import { getBufferTikTokChannel } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';

async function bufferGraphQL(query, variables = {}) {
  const apiKey = process.env.BUFFER_API_KEY;
  if (!apiKey) throw new Error('BUFFER_API_KEY is not configured.');

  const response = await fetch(BUFFER_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`
    },
    body: JSON.stringify({ query, variables })
  });

  const data = await response.json();
  if (!response.ok) throw new Error(`Buffer HTTP ${response.status}`);
  if (data.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
  return data.data;
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  try {
    const found = await getBufferTikTokChannel();
    if (!found) {
      return res.status(404).json({ ok: false, connected: false, message: 'No TikTok channel found in Buffer.' });
    }

    const postId = String(req.query?.post_id || '');
    let post = null;

    if (postId) {
      const data = await bufferGraphQL(
        `query GetPost($id: PostId!) {
          post(input: { id: $id }) {
            id
            text
            status
            dueAt
            sentAt
            externalLink
            error { message }
          }
        }`,
        { id: postId }
      );
      post = data?.post || null;
    }

    return res.status(200).json({
      ok: true,
      connected: true,
      organization: { id: found.organization.id, name: found.organization.name },
      channel: { id: found.channel.id, name: found.channel.name, service: found.channel.service },
      post
    });
  } catch (error) {
    return res.status(500).json({ ok: false, connected: false, message: error.message });
  }
}
