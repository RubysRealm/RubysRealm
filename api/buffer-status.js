import { getBufferTikTokChannel } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';
const RUBYCLIPS_CHANNEL_ID = '6a9f6ff1cd8b9c702c2897e1';

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

async function listTikTokChannels() {
  const account = await bufferGraphQL(`query { account { organizations { id name } } }`);
  const channels = [];
  for (const organization of account?.account?.organizations || []) {
    const data = await bufferGraphQL(
      `query GetChannels($organizationId: OrganizationId!) {
        channels(input: { organizationId: $organizationId }) {
          id
          name
          displayName
          service
          isQueuePaused
        }
      }`,
      { organizationId: organization.id }
    );
    for (const channel of data?.channels || []) {
      if (String(channel.service).toLowerCase() === 'tiktok') {
        channels.push({ organization, channel });
      }
    }
  }
  return channels;
}

async function getPost(postId) {
  const data = await bufferGraphQL(
    `query GetPost($id: PostId!) {
      post(input: { id: $id }) {
        id
        text
        status
        dueAt
        sentAt
        externalLink
        channel { id name displayName service }
        error { message }
      }
    }`,
    { id: postId }
  );
  return data?.post || null;
}

async function deletePost(postId) {
  const data = await bufferGraphQL(
    `mutation DeletePost($input: DeletePostInput!) {
      deletePost(input: $input) {
        ... on DeletePostSuccess { id }
        ... on VoidMutationError { message }
      }
    }`,
    { input: { id: postId } }
  );
  if (data?.deletePost?.message) throw new Error(data.deletePost.message);
  if (!data?.deletePost?.id) throw new Error('Buffer did not confirm post deletion.');
  return data.deletePost;
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  try {
    if (String(req.query?.all || '') === '1') {
      const channels = await listTikTokChannels();
      return res.status(200).json({ ok: true, channels });
    }

    const deleteId = String(req.query?.delete_post_id || '').trim();
    if (deleteId) {
      const post = await getPost(deleteId);
      if (!post) return res.status(404).json({ ok: false, deleted: false, message: 'Post not found.' });
      const channelId = String(post?.channel?.id || '');
      const text = String(post?.text || '');
      const isRubyClips = channelId === RUBYCLIPS_CHANNEL_ID && text.includes('#rubyclips');
      if (!isRubyClips) {
        return res.status(403).json({ ok: false, deleted: false, message: 'Deletion guard rejected a non-RubyClips post.' });
      }
      const deleted = await deletePost(deleteId);
      return res.status(200).json({ ok: true, deleted: true, id: deleted.id, previousStatus: post.status, externalLink: post.externalLink || null });
    }

    const found = await getBufferTikTokChannel();
    if (!found) {
      return res.status(404).json({ ok: false, connected: false, message: 'No TikTok channel found in Buffer.' });
    }

    const postId = String(req.query?.post_id || '');
    const post = postId ? await getPost(postId) : null;

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
