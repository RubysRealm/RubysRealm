import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';
const RELEASE_OWNER = 'RubysRealm';
const RELEASE_REPO = 'RubysRealm';
const ALLOWED_TARGETS = new Set(['rubaradaclips', 'takurada']);

async function gql(query, variables = {}) {
  const key = process.env.BUFFER_API_KEY;
  if (!key) throw new Error('BUFFER_API_KEY is not configured.');
  const r = await fetch(BUFFER_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
    body: JSON.stringify({ query, variables })
  });
  const d = await r.json();
  if (!r.ok) throw new Error(`Buffer HTTP ${r.status}`);
  if (d.errors?.length) throw new Error(d.errors.map(e => e.message).join('; '));
  return d.data;
}

async function recentPosts(target) {
  const d = await gql(
    `query Posts($organizationId: OrganizationId!, $channelId: ChannelId!) {
      posts(first: 60,input:{organizationId:$organizationId,filter:{status:[scheduled,sent],channelIds:[$channelId]},sort:[{field:createdAt,direction:desc}]}) {
        edges { node { id text status dueAt sentAt externalLink assets { source } } }
      }
    }`,
    { organizationId: target.organization.id, channelId: target.channel.id }
  );
  return (d?.posts?.edges || []).map(e => e.node);
}

function validateManifest(m) {
  if (m?.platform !== 'rubysrealm-promo-teaser-v1') throw new Error('Invalid promotion manifest.');
  const target = String(m?.targetChannel || '').replace(/^@/, '').toLowerCase();
  const source = String(m?.sourceChannel || '').replace(/^@/, '').toLowerCase();
  if (!ALLOWED_TARGETS.has(target) || !ALLOWED_TARGETS.has(source) || target === source) {
    throw new Error('Promotion channel guard rejected the source/target pair.');
  }
  if (!m?.sourceReleaseTag || !m?.file || !String(m.file).endsWith('.mp4')) {
    throw new Error('Promotion manifest is incomplete.');
  }
  const duration = Number(m?.durationSeconds || 0);
  if (!Number.isFinite(duration) || duration < 4 || duration > 30) {
    throw new Error('Promotion teaser duration must be 4-30 seconds.');
  }
  if (m?.ownedChannelsOnly !== true || m?.artificialEngagement !== false) {
    throw new Error('Promotion safety guard failed.');
  }
  return { target, source };
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });
  try {
    const tag = String(req.query?.tag || '').trim();
    if (!/^promo-[A-Za-z0-9._-]+$/.test(tag)) {
      return res.status(400).json({ ok: false, error: 'A valid promotion release tag is required.' });
    }

    const base = `https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
    const mr = await fetch(`${base}/manifest.json`, { redirect: 'follow', cache: 'no-store' });
    if (!mr.ok) throw new Error(`Promotion manifest unavailable (${mr.status}).`);
    const manifest = await mr.json();
    const { target, source } = validateManifest(manifest);

    const videoUrl = `${base}/${encodeURIComponent(manifest.file)}`;
    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow', cache: 'no-store' });
    if (!head.ok) throw new Error(`Promotion MP4 unavailable (${head.status}).`);

    const targetChannel = await getBufferTikTokChannel({ channelName: target, allowDisabled: true });
    if (!targetChannel) throw new Error(`Target @${target} is not connected in Buffer.`);
    const actual = String(targetChannel.channel.displayName || targetChannel.channel.name || '').replace(/^@/, '').toLowerCase();
    if (actual !== target) throw new Error(`Promotion channel guard rejected @${actual || 'unknown'}.`);

    const existing = await recentPosts(targetChannel);
    const duplicate = existing.find(p => p?.assets?.some(a => a?.source === videoUrl));
    const caption = String(manifest.caption || `From @${source} — full video on @${source} #rubysrealm`).trim().slice(0, 2200);

    if (duplicate) {
      return res.status(200).json({ ok: true, skipped: true, postId: duplicate.id, status: duplicate.status, externalLink: duplicate.externalLink || null, channelName: target, videoUrl });
    }

    const dueAt = new Date(Date.now() + 60 * 1000).toISOString();
    const post = await createBufferVideoPost({ channelId: targetChannel.channel.id, caption, videoUrl, dueAt, allowDisabled: true });
    return res.status(200).json({
      ok: true,
      postId: post.id,
      status: post.status,
      dueAt,
      channelName: target,
      sourceChannel: source,
      sourceReleaseTag: manifest.sourceReleaseTag,
      videoUrl
    });
  } catch (e) {
    console.error('promo-post failed', e);
    return res.status(500).json({ ok: false, error: e.message });
  }
}
