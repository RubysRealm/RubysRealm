import autoPost from './auto-post.js';
import { getBufferTikTokChannel } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function gql(query, variables = {}) {
  let lastError;
  for (let attempt = 0; attempt < 7; attempt++) {
    const response = await fetch(BUFFER_ENDPOINT, {
      method:'POST',
      headers:{ 'Content-Type':'application/json', Authorization:`Bearer ${process.env.BUFFER_API_KEY}` },
      body:JSON.stringify({ query, variables })
    });

    if (response.status === 429) {
      const retryAfter = Number(response.headers.get('retry-after'));
      const waitMs = Number.isFinite(retryAfter) && retryAfter > 0
        ? Math.min(retryAfter * 1000, 60000)
        : Math.min(2500 * (2 ** attempt), 45000);
      lastError = new Error(`Buffer HTTP 429; retrying after ${waitMs}ms`);
      await sleep(waitMs);
      continue;
    }

    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(`Buffer HTTP ${response.status}`);
    if (data.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
    return data.data;
  }
  throw lastError || new Error('Buffer rate limit did not clear.');
}

async function scheduledPosts(found) {
  const data = await gql(
    `query Scheduled($organizationId: OrganizationId!, $channelId: ChannelId!) {
      posts(first: 20, input: {
        organizationId: $organizationId,
        filter: { status: [scheduled], channelIds: [$channelId] },
        sort: [{ field: dueAt, direction: asc }]
      }) { edges { node { id text dueAt } } }
    }`,
    { organizationId:found.organization.id, channelId:found.channel.id }
  );
  return (data?.posts?.edges || []).map(edge => edge.node);
}

async function deletePost(id) {
  const data = await gql(
    `mutation DeleteScheduled($id: PostId!) {
      deletePost(input: { id: $id }) {
        ... on DeletePostSuccess { id }
        ... on VoidMutationError { message }
      }
    }`,
    { id }
  );
  if (data?.deletePost?.message) throw new Error(data.deletePost.message);
  return data?.deletePost?.id || id;
}

export default async function handler(req, res) {
  const mode = String(req.query?.mode || 'rebuild');
  try {
    const found = await getBufferTikTokChannel();
    if (!found) return res.status(404).json({ ok:false, error:'No TikTok channel found.' });
    if (mode === 'inspect') return res.status(200).json({ ok:true, posts:await scheduledPosts(found) });
    if (mode === 'clear' || mode === 'rebuild') {
      const posts = await scheduledPosts(found);
      const deleted = [];
      for (const post of posts) {
        deleted.push(await deletePost(post.id));
        await sleep(1200);
      }
      if (mode === 'clear') return res.status(200).json({ ok:true, deleted, remaining:await scheduledPosts(found) });
      await sleep(2500);
      req.headers['x-vercel-cron'] = '1';
      return autoPost(req, res);
    }
    return res.status(400).json({ ok:false, error:'Unknown mode' });
  } catch (error) {
    return res.status(500).json({ ok:false, error:error.message });
  }
}
