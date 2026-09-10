import { getBufferYouTubeChannel, recentYouTubePosts, createBufferYouTubeShort } from '../lib/buffer-youtube.js';

const RELEASE_OWNER = 'RubysRealm';
const RELEASE_REPO = 'RubysRealm';

function validateManifest(m) {
  if (m?.pipeline !== 'rubys-realm-podcast-repurpose-v1') {
    throw new Error('Blocked: invalid YouTube source manifest.');
  }
  if (!m?.qualityPassed) throw new Error('Blocked: source quality gate did not pass.');
  const part = Number(m.part);
  const total = Number(m.totalParts);
  const duration = Number(m.durationSeconds);
  if (!Number.isInteger(part) || !Number.isInteger(total) || part < 1 || total < 1 || part > total) {
    throw new Error('Blocked: invalid part numbering.');
  }
  if (!Number.isFinite(duration) || duration < 30 || duration > 180) {
    throw new Error('Blocked: YouTube Short must be between 30 and 180 seconds.');
  }
  if (Number(m.width) !== 1080 || Number(m.height) !== 1920) {
    throw new Error('Blocked: YouTube Short is not 1080x1920.');
  }
  if (!m?.source?.id || !m?.source?.title || !m?.video || !String(m.video).endsWith('.mp4')) {
    throw new Error('Blocked: YouTube source manifest is incomplete.');
  }
}

function cleanTitle(text) {
  return String(text || 'Ruby’s Realm').replace(/\s+/g, ' ').trim();
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });

  try {
    const target = await getBufferYouTubeChannel();
    if (!target) {
      return res.status(404).json({
        ok: false,
        connected: false,
        message: 'No YouTube channel is connected in Buffer yet.'
      });
    }

    const tag = String(req.query?.tag || '').trim();
    if (!tag) {
      return res.status(200).json({
        ok: true,
        connected: true,
        organization: { id: target.organization.id, name: target.organization.name },
        channel: {
          id: target.channel.id,
          name: target.channel.name,
          displayName: target.channel.displayName,
          service: target.channel.service,
          isQueuePaused: target.channel.isQueuePaused
        }
      });
    }

    if (!/^youtube-part-[A-Za-z0-9._-]+$/.test(tag)) {
      throw new Error('A valid YouTube release tag is required.');
    }

    const base = `https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
    const manifestResponse = await fetch(`${base}/manifest.json`, { redirect: 'follow', cache: 'no-store' });
    if (!manifestResponse.ok) throw new Error(`YouTube manifest unavailable (${manifestResponse.status}).`);
    const manifest = await manifestResponse.json();
    validateManifest(manifest);

    const fileName = String(manifest.video).split('/').pop();
    const videoUrl = `${base}/${encodeURIComponent(fileName)}`;
    const head = await fetch(videoUrl, { method: 'HEAD', redirect: 'follow', cache: 'no-store' });
    if (!head.ok) throw new Error(`YouTube MP4 unavailable (${head.status}).`);

    const posts = await recentYouTubePosts(target, 60);
    const duplicate = posts.find(post => post?.assets?.some(asset => asset?.source === videoUrl));
    const storyTitle = cleanTitle(manifest.source.title);
    const title = `${storyTitle} | Part ${manifest.part}/${manifest.totalParts}`.slice(0, 100);
    const description = `${storyTitle}\nPart ${manifest.part} of ${manifest.totalParts}\n\n#Shorts #Storytime #RubysRealm`;

    if (duplicate) {
      return res.status(200).json({
        ok: true,
        skipped: true,
        postId: duplicate.id,
        status: duplicate.status,
        externalLink: duplicate.externalLink || null,
        channelName: target.channel.displayName || target.channel.name,
        title,
        videoUrl
      });
    }

    const dueAt = new Date(Date.now() + 60 * 1000).toISOString();
    const post = await createBufferYouTubeShort({
      channelId: target.channel.id,
      title,
      description,
      videoUrl,
      dueAt
    });

    return res.status(200).json({
      ok: true,
      connected: true,
      postId: post.id,
      status: post.status,
      dueAt,
      channelName: target.channel.displayName || target.channel.name,
      title,
      storyId: manifest.source.id,
      partNumber: Number(manifest.part),
      totalParts: Number(manifest.totalParts),
      videoUrl
    });
  } catch (error) {
    return res.status(500).json({ ok: false, connected: false, message: error.message });
  }
}
