import { previewStory } from '../content/story-engine.js';
import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT = 'https://api.buffer.com';
const DAILY_POSTS = 6;
const SLOT_HOURS_UTC = [13, 16, 19, 22, 25, 28]; // 9am, noon, 3pm, 6pm, 9pm, midnight ET during EDT
const LONG_SLOT_INDEX = 4; // one extended story each day, currently the 9pm ET slot

function isAuthorized(req) {
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) return req.headers.authorization === `Bearer ${cronSecret}`;
  return req.headers['x-vercel-cron'] === '1' || req.headers['x-vercel-cron'] === 'true';
}

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

async function scheduledPosts(target) {
  const data = await bufferGraphQL(
    `query Scheduled($organizationId: OrganizationId!, $channelId: ChannelId!) {
      posts(first: 20, input: {
        organizationId: $organizationId,
        filter: { status: [scheduled], channelIds: [$channelId] },
        sort: [{ field: dueAt, direction: asc }]
      }) {
        edges { node { id text dueAt assets { source } } }
      }
    }`,
    { organizationId: target.organization.id, channelId: target.channel.id }
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
  return Array.from({ length: DAILY_POSTS }, (_, slot) => {
    const seed = `${day}-slot-${slot + 1}`;
    const isLong = slot === LONG_SLOT_INDEX;
    return { seed, isLong, preview:previewStory(seed,{ long:isLong }) };
  });
}

function captionFor(item) {
  const genre = item.preview.genre.replaceAll('-',' ');
  const lengthNote = item.isLong ? ' Extended story.' : '';
  return `${item.preview.title}. An animated ${genre} story with a twist.${lengthNote} Watch to the end. #RubysRealm #AnimatedStory #TalkingCharacters #StoryTok #AIGenerated`;
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });
  if (!isAuthorized(req)) return res.status(401).json({ error: 'Unauthorized' });

  try {
    const target = await getBufferTikTokChannel();
    if (!target) return res.status(404).json({ error: 'No TikTok channel connected in Buffer.' });

    const origin = process.env.PUBLIC_BASE_URL || 'https://rubys-realm.vercel.app';
    const items = storiesForToday();
    const slots = scheduledSlots();
    const existing = await scheduledPosts(target);
    const created = [];
    const skipped = [];

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      const videoUrl = `${origin}/api/story-video?seed=${encodeURIComponent(item.seed)}${item.isLong ? '&long=1' : ''}`;
      const dueAt = slots[i].toISOString();
      const caption = captionFor(item);
      const duplicate = existing.find(post =>
        post?.assets?.some(asset => asset?.source === videoUrl) ||
        (post?.dueAt === dueAt && post?.text === caption)
      );

      if (duplicate) {
        skipped.push({ seed:item.seed, postId:duplicate.id, dueAt, reason:'already-scheduled' });
        continue;
      }

      const preflight = await fetch(videoUrl,{ method:'HEAD' });
      if (!preflight.ok || preflight.headers.get('x-rubys-realm-format') !== 'animated-story-v2') {
        throw new Error(`Animated video preflight failed for ${item.seed}.`);
      }

      const post = await createBufferVideoPost({
        channelId: target.channel.id,
        caption,
        videoUrl,
        dueAt
      });

      created.push({
        seed:item.seed,
        title:item.preview.title,
        genre:item.preview.genre,
        renderer:'animated-story-v2',
        lengthClass:item.isLong ? 'extended-story' : 'story',
        videoUrl,
        dueAt,
        postId:post.id,
        status:post.status
      });
      existing.push({ id:post.id, text:caption, dueAt, assets:[{ source:videoUrl }] });
    }

    return res.status(200).json({
      ok:true,
      dailyPosts:DAILY_POSTS,
      extendedStoriesPerDay:1,
      format:{
        animatedAdults:true,
        distinctVoices:true,
        visibleTalking:true,
        physicalActions:true,
        captions:true,
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
