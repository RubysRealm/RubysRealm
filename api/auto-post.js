import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';
const MIN_DURATION_SECONDS = 120;
const MAX_DURATION_SECONDS = 540;
const REQUIRED_RENDERER = 'fully-animated-scene-v1';
const REQUIRED_QUALITY_GATE = 'animated-dialogue-clean-screen-required';
const RELEASE_OWNER = 'RubysRealm';
const RELEASE_REPO = 'RubysRealm';

function isAuthorized(req) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) return req.headers.authorization === `Bearer ${cronSecret}`;
  return req.headers['x-vercel-cron'] === '1' || req.headers['x-vercel-cron'] === 'true';
}

async function bufferGraphQL(query, variables = {}) {
  const apiKey = process.env.BUFFER_API_KEY;
  if (!apiKey) throw new Error('BUFFER_API_KEY is not configured.');
  const response = await fetch(BUFFER_ENDPOINT, {
    method:'POST',
    headers:{ 'Content-Type':'application/json', Authorization:`Bearer ${apiKey}` },
    body:JSON.stringify({ query, variables })
  });
  const data = await response.json();
  if (!response.ok) throw new Error(`Buffer HTTP ${response.status}`);
  if (data.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
  return data.data;
}

async function scheduledPosts(target) {
  const data = await bufferGraphQL(
    `query Scheduled($organizationId: OrganizationId!, $channelId: ChannelId!) {
      posts(first: 20, input: {
        organizationId: $organizationId,
        filter: { status: [scheduled], channelIds: [$channelId] },
        sort: [{ field: dueAt, direction: asc }]
      }) { edges { node { id text dueAt assets { source } } } }
    }`,
    { organizationId:target.organization.id, channelId:target.channel.id }
  );
  return (data?.posts?.edges || []).map(edge => edge.node);
}

function validateManifest(manifest) {
  if (!manifest || manifest.renderer !== REQUIRED_RENDERER) throw new Error('Blocked: video is not from the fully animated scene renderer.');
  if (manifest.qualityGate !== REQUIRED_QUALITY_GATE) throw new Error('Blocked: required animation/text quality gate did not pass.');
  if (manifest.fullyAnimatedPeople !== true) throw new Error('Blocked: characters are not confirmed fully animated.');
  if (manifest.visibleDialogue !== true) throw new Error('Blocked: visible character-to-character dialogue is required.');
  if (manifest.storyMatchedEnvironments !== true) throw new Error('Blocked: story-matched environments are required.');
  if (manifest.noStillImageVoiceover !== true) throw new Error('Blocked: still-image voiceover format is prohibited.');
  if (manifest.cleanScreenTextPassed !== true) throw new Error('Blocked: stray/unplanned on-screen text detected or not verified.');
  if (manifest.onlyIntentionalCaptions !== true) throw new Error('Blocked: only intentional captions/subtitles are permitted.');
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error:'Method not allowed' });
  if (!isAuthorized(req)) return res.status(401).json({ error:'Unauthorized' });

  try {
    const target = await getBufferTikTokChannel();
    if (!target) return res.status(404).json({ error:'No TikTok channel connected in Buffer.' });

    const day = String(req.query?.day || new Date().toISOString().slice(0,10));
    const tag = `animated-stories-${day}`;
    const manifestUrl = `https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${tag}/manifest.json`;
    const response = await fetch(manifestUrl, { redirect:'follow', cache:'no-store' });
    if (!response.ok) throw new Error(`No approved fully animated release is ready for ${day}.`);
    const manifest = await response.json();
    validateManifest(manifest);

    const videoUrl = `https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${tag}/${manifest.file || 'story.mp4'}`;
    const duration = Number(manifest.durationSeconds);
    if (!Number.isFinite(duration) || duration < MIN_DURATION_SECONDS || duration > MAX_DURATION_SECONDS) {
      throw new Error('Blocked: final video is outside the required 2-9 minute range.');
    }

    const existing = await scheduledPosts(target);
    const duplicate = existing.find(post => post?.assets?.some(asset => asset?.source === videoUrl));
    if (duplicate) return res.status(200).json({ ok:true, skipped:true, reason:'already-scheduled', postId:duplicate.id });

    const fileCheck = await fetch(videoUrl, { method:'HEAD', redirect:'follow' });
    if (!fileCheck.ok) throw new Error('Approved animated MP4 is unavailable.');

    const dueAt = manifest.dueAt || new Date(Date.now() + 20 * 60000).toISOString();
    const caption = String(manifest.caption || 'Ruby\'s Realm animated story. #StoryTok #AIGenerated');
    const post = await createBufferVideoPost({ channelId:target.channel.id, caption, videoUrl, dueAt });

    return res.status(200).json({
      ok:true,
      renderer:REQUIRED_RENDERER,
      fullyAnimatedPeople:true,
      visibleDialogue:true,
      storyMatchedEnvironments:true,
      noStillImageVoiceover:true,
      cleanScreenTextPassed:true,
      onlyIntentionalCaptions:true,
      automaticPosting:true,
      videoUrl,
      dueAt,
      postId:post.id,
      status:post.status
    });
  } catch (error) {
    console.error('auto-post failed', error);
    return res.status(500).json({ ok:false, error:error.message });
  }
}
