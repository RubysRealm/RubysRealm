import { previewStory } from '../content/story-engine.js';
import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';
const DAILY_POSTS = 6;
const SLOT_HOURS_UTC = [13, 16, 19, 22, 25, 28]; // 9am, noon, 3pm, 6pm, 9pm, midnight ET during EDT
const MIN_DURATION_SECONDS = 120;
const MAX_DURATION_SECONDS = 540;

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
    return { seed, preview:previewStory(seed) };
  });
}

function captionFor(item) {
  const genre = item.preview.genre.replaceAll('-',' ');
  return `${item.preview.title}. Full ${item.preview.targetMinutes}-minute animated ${genre} story with talking characters. Watch to the end. #RubysRealm #AnimatedStory #TalkingCharacters #StoryTok #AIGenerated`;
}

async function mapLimit(items, limit, worker) {
  const output = new Array(items.length);
  let cursor = 0;
  async function runOne() {
    while (cursor < items.length) {
      const index = cursor++;
      output[index] = await worker(items[index], index);
    }
  }
  await Promise.all(Array.from({ length:Math.min(limit, items.length) }, runOne));
  return output;
}

async function warmAndVerifyVideo(item) {
  const response = await fetch(item.videoUrl, { method:'GET' });
  if (!response.ok) throw new Error(`Video render failed for ${item.seed}: HTTP ${response.status}`);
  if (response.headers.get('x-rubys-realm-format') !== 'animated-story-v2') {
    throw new Error(`Unexpected render format for ${item.seed}.`);
  }
  const duration = Number(response.headers.get('x-rubys-realm-duration'));
  await response.arrayBuffer();
  if (!Number.isFinite(duration)) throw new Error(`Rendered duration missing for ${item.seed}.`);
  if (duration < MIN_DURATION_SECONDS || duration > MAX_DURATION_SECONDS) {
    throw new Error(`Rendered duration ${duration.toFixed(1)}s is outside 2-9 minutes for ${item.seed}.`);
  }
  return duration;
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error:'Method not allowed' });
  if (!isAuthorized(req)) return res.status(401).json({ error:'Unauthorized' });

  try {
    const target = await getBufferTikTokChannel();
    if (!target) return res.status(404).json({ error:'No TikTok channel connected in Buffer.' });

    const origin = process.env.PUBLIC_BASE_URL || 'https://rubys-realm.vercel.app';
    const stories = storiesForToday();
    const slots = scheduledSlots();
    const existing = await scheduledPosts(target);

    const prepared = stories.map((item, index) => ({
      ...item,
      videoUrl:`${origin}/api/story-video?seed=${encodeURIComponent(item.seed)}`,
      dueAt:slots[index].toISOString(),
      caption:captionFor(item)
    }));

    const renderDurations = await mapLimit(prepared, 3, warmAndVerifyVideo);
    prepared.forEach((item, index) => { item.actualDurationSeconds = renderDurations[index]; });

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
        renderer:'animated-story-v2',
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
      format:{
        fullStories:true,
        animatedAdults:true,
        distinctVoices:true,
        visibleTalking:true,
        physicalActions:true,
        captions:true,
        durationDriven:true,
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
