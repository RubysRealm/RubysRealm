import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';
const RUBYCLIPS_CHANNEL_ID = '6a9f6ff1cd8b9c702c2897e1';
const RELEASE_OWNER = 'RubysRealm';
const RELEASE_REPO = 'RubysRealm';
const ALLOWED_PROMO_TARGETS = new Set(['rubaradaclips', 'takurada']);

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
        assets { source }
        channel { id name displayName service }
        error { message }
      }
    }`,
    { id: postId }
  );
  return data?.post || null;
}

async function recentPostsForChannel(target, first = 40, statuses = ['sent']) {
  const data = await bufferGraphQL(
    `query RecentPosts($organizationId: OrganizationId!, $channelId: ChannelId!, $first: Int!, $statuses: [PostStatus!]) {
      posts(first: $first, input: {
        organizationId: $organizationId,
        filter: { status: $statuses, channelIds: [$channelId] },
        sort: [{ field: createdAt, direction: desc }]
      }) {
        edges {
          node {
            id
            text
            status
            dueAt
            sentAt
            externalLink
            assets { source }
            channel { id name displayName service }
          }
        }
      }
    }`,
    {
      organizationId: target.organization.id,
      channelId: target.channel.id,
      first: Math.min(60, Math.max(1, Number(first) || 40)),
      statuses
    }
  );
  return (data?.posts?.edges || []).map(edge => edge.node);
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

function validatePromotionManifest(m) {
  if (m?.platform !== 'rubysrealm-promo-teaser-v1') throw new Error('Invalid promotion manifest.');
  const target = String(m?.targetChannel || '').replace(/^@/, '').toLowerCase();
  const source = String(m?.sourceChannel || '').replace(/^@/, '').toLowerCase();
  if (!ALLOWED_PROMO_TARGETS.has(target) || !ALLOWED_PROMO_TARGETS.has(source) || target === source) {
    throw new Error('Promotion channel guard rejected the source/target pair.');
  }
  if (!m?.sourceReleaseTag || !m?.file || !String(m.file).endsWith('.mp4')) throw new Error('Promotion manifest is incomplete.');
  const duration = Number(m?.durationSeconds || 0);
  if (!Number.isFinite(duration) || duration < 4 || duration > 30) throw new Error('Promotion teaser duration must be 4-30 seconds.');
  if (m?.ownedChannelsOnly !== true || m?.artificialEngagement !== false) throw new Error('Promotion safety guard failed.');
  return { target, source };
}

async function postPromotion(tag) {
  if (!/^promo-[A-Za-z0-9._-]+$/.test(tag)) throw new Error('A valid promotion release tag is required.');
  const base = `https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
  const mr = await fetch(`${base}/manifest.json`, { redirect: 'follow', cache: 'no-store' });
  if (!mr.ok) throw new Error(`Promotion manifest unavailable (${mr.status}).`);
  const manifest = await mr.json();
  const { target, source } = validatePromotionManifest(manifest);
  const videoUrl = `${base}/${encodeURIComponent(manifest.file)}`;
  const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow', cache: 'no-store' });
  if (!head.ok) throw new Error(`Promotion MP4 unavailable (${head.status}).`);

  const targetChannel = await getBufferTikTokChannel({ channelName: target, allowDisabled: true });
  if (!targetChannel) throw new Error(`Target @${target} is not connected in Buffer.`);
  const actual = String(targetChannel.channel.displayName || targetChannel.channel.name || '').replace(/^@/, '').toLowerCase();
  if (actual !== target) throw new Error(`Promotion channel guard rejected @${actual || 'unknown'}.`);

  const existing = await recentPostsForChannel(targetChannel, 60, ['scheduled', 'sent']);
  const duplicate = existing.find(p => p?.assets?.some(a => a?.source === videoUrl));
  const caption = String(manifest.caption || `From @${source} — full video on @${source} #rubysrealm`).trim().slice(0, 2200);
  if (duplicate) {
    return { ok: true, skipped: true, postId: duplicate.id, status: duplicate.status, externalLink: duplicate.externalLink || null, channelName: target, videoUrl };
  }

  const dueAt = new Date(Date.now() + 60 * 1000).toISOString();
  const post = await createBufferVideoPost({ channelId: targetChannel.channel.id, caption, videoUrl, dueAt, allowDisabled: true });
  return { ok: true, postId: post.id, status: post.status, dueAt, channelName: target, sourceChannel: source, sourceReleaseTag: manifest.sourceReleaseTag, videoUrl };
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  try {
    if (String(req.query?.all || '') === '1') {
      const channels = await listTikTokChannels();
      return res.status(200).json({ ok: true, channels });
    }

    const promoTag = String(req.query?.promo_tag || '').trim();
    if (promoTag) {
      const result = await postPromotion(promoTag);
      return res.status(200).json(result);
    }

    const recentChannel = String(req.query?.recent_channel || '').trim().replace(/^@/, '');
    if (recentChannel) {
      const target = await getBufferTikTokChannel({ channelName: recentChannel, allowDisabled: true });
      if (!target) return res.status(404).json({ ok: false, message: `TikTok channel @${recentChannel} not found.` });
      const posts = await recentPostsForChannel(target, req.query?.limit, ['sent']);
      return res.status(200).json({
        ok: true,
        channel: { id: target.channel.id, name: target.channel.name, displayName: target.channel.displayName },
        posts
      });
    }

    const deleteId = String(req.query?.delete_post_id || '').trim();
    if (deleteId) {
      const post = await getPost(deleteId);
      if (!post) return res.status(404).json({ ok: false, deleted: false, message: 'Post not found.' });
      const channelId = String(post?.channel?.id || '');
      const text = String(post?.text || '');
      const isRubyClips = channelId === RUBYCLIPS_CHANNEL_ID && text.includes('#rubyclips');
      if (!isRubyClips) return res.status(403).json({ ok: false, deleted: false, message: 'Deletion guard rejected a non-RubyClips post.' });
      const deleted = await deletePost(deleteId);
      return res.status(200).json({ ok: true, deleted: true, id: deleted.id, previousStatus: post.status, externalLink: post.externalLink || null });
    }

    const found = await getBufferTikTokChannel();
    if (!found) return res.status(404).json({ ok: false, connected: false, message: 'No TikTok channel found in Buffer.' });

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
