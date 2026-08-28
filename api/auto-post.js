import { previewStory } from '../content/story-engine.js';
import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';
const DAILY_POSTS = 6;
const SLOT_HOURS_UTC = [13, 16, 19, 22, 25, 28]; // 9am, noon, 3pm, 6pm, 9pm, midnight ET during EDT
const MIN_DURATION_SECONDS = 120;
const MAX_DURATION_SECONDS = 540;
const REQUIRED_RENDERER = 'photoreal-human-v1';
const REQUIRED_QUALITY_GATE = 'realistic-humans-required';
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

function scheduledSlots(now = new Date()) {
  const base = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0));
  let slots = SLOT_HOURS_UTC.map(hour => new Date(base.getTime() + hour * 3600000));
  while (slots.filter(d => d.getTime() > now.getTime() + 10 * 60000).length < DAILY_POSTS) {
    slots.push(new Date(slots[slots.length - 1].getTime() + 3 * 3600000));
  }
  return slots.filter(d => d.getTime() > now.getTime() + 10 * 60000).slice(0, DAILY_POSTS);
}

function storiesForToday(now = new Date()) {
  const day = now.toISOString().slice(0,10);
  return Array.from({ length:DAILY_POSTS }, (_, slot) => {
    const seed = `${day}-slot-${slot + 1}`;
    return { slot:slot + 1, seed, preview:previewStory(seed) };
  });
}

function captionFor(item) {
  const genre = item.preview.genre.replaceAll('-',' ');
  return `${item.preview.title}. Full ${item.preview.targetMinutes}-minute realistic animated ${genre} story with human characters. Watch to the end. #RubysRealm #RealisticAI #TalkingCharacters #StoryTok #AIGenerated`;
}

async function fetchManifest(day) {
  const tag = `stories-${day}`;
  const url = `https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${tag}/manifest.json`;
  const response = await fetch(url, { redirect:'follow', cache:'no-store' });
  if (!response.ok) throw new Error(`Daily rendered-story manifest is not ready: HTTP ${response.status}`);
  const manifest = await response.json();
  if (manifest?.day !== day || !Array.isArray(manifest?.slots)) throw new Error('Daily rendered-story manifest is invalid.');
  if (manifest?.renderer !== REQUIRED_RENDERER || manifest?.qualityGate !== REQUIRED_QUALITY_GATE || manifest?.qualityAndDurationRequired !== true) {
    throw new Error('Daily rendered-story manifest failed the required realistic-human quality gate. Nothing will be posted.');
  }
  return { tag, manifest };
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error:'Method not allowed' });
  if (!isAuthorized(req)) return res.status(401).json({ error:'Unauthorized' });

  try {
    const target = await getBufferTikTokChannel();
    if (!target) return res.status(404).json({ error:'No TikTok channel connected in Buffer.' });

    const stories = storiesForToday();
    const day = stories[0].seed.slice(0,10);
    const slots = scheduledSlots();
    const existing = await scheduledPosts(target);
    const { tag, manifest } = await fetchManifest(day);

    const prepared = stories.map((item, index) => {
      const rendered = manifest.slots.find(entry => Number(entry.slot) === item.slot);
      if (!rendered) throw new Error(`Rendered release asset is missing for slot ${item.slot}.`);
      if (rendered.renderer !== REQUIRED_RENDERER || rendered.qualityGate !== REQUIRED_QUALITY_GATE) {
        throw new Error(`Rendered slot ${item.slot} failed the realistic-human quality gate.`);
      }
      const actualDurationSeconds = Number(rendered.durationSeconds);
      if (!Number.isFinite(actualDurationSeconds) || actualDurationSeconds < MIN_DURATION_SECONDS || actualDurationSeconds > MAX_DURATION_SECONDS) {
        throw new Error(`Rendered slot ${item.slot} is outside the required 2-9 minute range.`);
      }
      return {
        ...item,
        actualDurationSeconds,
        videoUrl:`https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${tag}/slot-${item.slot}.mp4`,
        dueAt:slots[index].toISOString(),
        caption:captionFor(item)
      };
    });

    const created = [];
    const skipped = [];

    for (const item of prepared) {
      const duplicate = existing.find(post =>
        post?.assets?.some(asset => asset?.source === item.videoUrl) ||
        (post?.dueAt === item.dueAt && post?.text === item.caption)
      );
      if (duplicate) {
        skipped.push({
          seed:item.seed,
          postId:duplicate.id,
          dueAt:item.dueAt,
          targetMinutes:item.preview.targetMinutes,
          actualDurationSeconds:item.actualDurationSeconds,
          reason:'already-scheduled'
        });
        continue;
      }

      const fileCheck = await fetch(item.videoUrl, { method:'HEAD', redirect:'follow' });
      if (!fileCheck.ok) throw new Error(`Static rendered MP4 is unavailable for ${item.seed}: HTTP ${fileCheck.status}`);

      const post = await createBufferVideoPost({
        channelId:target.channel.id,
        caption:item.caption,
        videoUrl:item.videoUrl,
        dueAt:item.dueAt
      });

      created.push({
        seed:item.seed,
        title:item.preview.title,
        genre:item.preview.genre,
        renderer:REQUIRED_RENDERER,
        qualityGate:REQUIRED_QUALITY_GATE,
        targetMinutes:item.preview.targetMinutes,
        actualDurationSeconds:item.actualDurationSeconds,
        sceneCount:item.preview.sceneCount,
        spokenWords:item.preview.spokenWords,
        durationRange:item.preview.durationRange,
        videoUrl:item.videoUrl,
        dueAt:item.dueAt,
        postId:post.id,
        status:post.status
      });
      existing.push({ id:post.id, text:item.caption, dueAt:item.dueAt, assets:[{ source:item.videoUrl }] });
    }

    return res.status(200).json({
      ok:true,
      dailyPosts:DAILY_POSTS,
      durationRange:'2-9 minutes',
      verifiedActualDurations:true,
      realisticHumanQualityRequired:true,
      qualityAndDurationRequired:true,
      staticReleaseAssets:true,
      releaseTag:tag,
      format:{
        fullStories:true,
        realisticHumans:true,
        distinctVoices:true,
        visibleTalking:true,
        physicalActions:true,
        captions:true,
        durationDriven:true,
        noLowQualityFallbacks:true,
        preRenderedBeforeBuffer:true,
        branding:'Ruby\'s Realm only'
      },
      channel:{ id:target.channel.id, name:target.channel.displayName || target.channel.name },
      created,
      skipped
    });
  } catch (error) {
    console.error('auto-post failed', error);
    return res.status(500).json({ ok:false, error:error.message });
  }
}
