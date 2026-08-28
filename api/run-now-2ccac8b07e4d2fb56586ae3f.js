import autoPost from './auto-post.js';
import { getBufferTikTokChannel } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';

async function gql(query, variables = {}) {
  const response = await fetch(BUFFER_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${process.env.BUFFER_API_KEY}`
    },
    body: JSON.stringify({ query, variables })
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`Buffer HTTP ${response.status}`);
  if (data.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
  return data.data;
}

export default async function handler(req, res) {
  if (String(req.query?.mode || '') === 'inspect') {
    try {
      const found = await getBufferTikTokChannel();
      if (!found) return res.status(404).json({ ok:false, error:'No TikTok channel found.' });
      const data = await gql(
        `query Scheduled($organizationId: OrganizationId!, $channelId: ChannelId!) {
          posts(first: 20, input: {
            organizationId: $organizationId,
            filter: { status: [scheduled], channelIds: [$channelId] },
            sort: [{ field: dueAt, direction: asc }]
          }) {
            edges { node { id text status dueAt channelId assets { id mimeType source type } } }
          }
        }`,
        { organizationId: found.organization.id, channelId: found.channel.id }
      );
      return res.status(200).json({ ok:true, channel:found.channel, posts:(data?.posts?.edges || []).map(e => e.node) });
    } catch (error) {
      return res.status(500).json({ ok:false, error:error.message });
    }
  }

  req.headers['x-vercel-cron'] = '1';
  return autoPost(req, res);
}
