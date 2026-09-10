const BUFFER_ENDPOINT = 'https://api.buffer.com';
const LEGACY_TIKTOK_CHANNEL = 'takurada';
const DISABLED_TIKTOK_CHANNELS = new Set(['rubaradaclips']);
const DISABLED_CHANNEL_IDS = new Set(['6a9f6ff1cd8b9c702c2897e1']);
const TIKTOK_TRENDS_URL = 'https://ads.tiktok.com/business/creativecenter/hashtag/a56/pc/en?countryCode=US&period=7';
const TREND_CACHE_MS = 30 * 60 * 1000;
const FALLBACK_TRENDING_HASHTAGS = ['#fyp', '#viral', '#storytime'];
let trendCache = { expiresAt: 0, tags: [] };

function normalizeHashtag(value) {
  const cleaned = String(value || '')
    .trim()
    .replace(/^#/, '')
    .replace(/[^A-Za-z0-9_]/g, '');
  if (!/^[A-Za-z][A-Za-z0-9_]{1,39}$/.test(cleaned)) return null;
  return `#${cleaned.toLowerCase()}`;
}

function uniqueHashtags(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const tag = normalizeHashtag(value);
    if (!tag || seen.has(tag)) continue;
    seen.add(tag);
    result.push(tag);
  }
  return result;
}

async function getTrendingTikTokHashtags(limit = 3) {
  const wanted = Math.max(1, Math.min(5, Number(limit) || 3));
  const now = Date.now();
  if (trendCache.expiresAt > now && trendCache.tags.length) {
    return trendCache.tags.slice(0, wanted);
  }

  const discovered = [];
  try {
    const response = await fetch(TIKTOK_TRENDS_URL, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; RubysRealmPublisher/1.0)',
        Accept: 'text/html,application/xhtml+xml'
      },
      cache: 'no-store'
    });
    if (response.ok) {
      const html = await response.text();
      const patterns = [
        /"hashtagName"\s*:\s*"([A-Za-z][A-Za-z0-9_]{1,39})"/gi,
        /"hashtag_name"\s*:\s*"([A-Za-z][A-Za-z0-9_]{1,39})"/gi,
        />\s*#([A-Za-z][A-Za-z0-9_]{1,39})\s*</g,
        /\\u0023([A-Za-z][A-Za-z0-9_]{1,39})/g
      ];
      for (const pattern of patterns) {
        let match;
        while ((match = pattern.exec(html)) !== null && discovered.length < 20) {
          discovered.push(match[1]);
        }
        if (discovered.length >= 20) break;
      }
    }
  } catch {
    // Falling back to broad discovery hashtags is intentional if Creative Center is unavailable.
  }

  const tags = uniqueHashtags([...discovered, ...FALLBACK_TRENDING_HASHTAGS]).slice(0, 5);
  trendCache = { expiresAt: now + TREND_CACHE_MS, tags };
  return tags.slice(0, wanted);
}

async function withTrendingHashtags(caption, limit = 3) {
  const base = String(caption || '').trim();
  const trends = await getTrendingTikTokHashtags(limit);
  const existing = new Set((base.match(/#[A-Za-z0-9_]+/g) || []).map(t => t.toLowerCase()));
  const additions = trends.filter(tag => !existing.has(tag.toLowerCase()));
  if (!additions.length) return base.slice(0, 2200);

  const suffix = ` ${additions.join(' ')}`;
  const maxBase = Math.max(0, 2200 - suffix.length);
  return `${base.slice(0, maxBase).trimEnd()}${suffix}`.trim().slice(0, 2200);
}

function normalizePostIdentity(value) {
  let text = String(value || '')
    .toLowerCase()
    .replace(/#[a-z0-9_]+/gi, ' ')
    .replace(/[–—]/g, '-')
    .replace(/\s+/g, ' ')
    .trim();

  text = text
    .replace(/\s+-\s+(\d+\s*\/\s*\d+)\s*$/i, ' - part $1')
    .replace(/\s+-\s+part\s+(\d+)\s*\/\s*(\d+)/gi, ' - part $1/$2')
    .replace(/\s*\|\s*part\s+(\d+)\s*\/\s*(\d+)/gi, ' - part $1/$2')
    .replace(/\s+/g, ' ')
    .trim();

  return text;
}

async function gql(query, variables = {}) {
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

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const retryAfter = Number(response.headers.get('retry-after') || 0);
    const windowName = data?.errors?.[0]?.extensions?.window || null;
    const error = new Error(`Buffer HTTP ${response.status}${windowName ? ` (${windowName})` : ''}`);
    error.status = response.status;
    error.retryAfter = Number.isFinite(retryAfter) ? retryAfter : 0;
    error.rateLimitWindow = windowName;
    throw error;
  }
  if (data?.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
  return data?.data;
}

export async function getBufferTikTokChannel(options = {}) {
  const requestedId = String(options.channelId || '').trim();
  const requestedName = String(
    options.channelName || process.env.BUFFER_TIKTOK_CHANNEL_NAME || LEGACY_TIKTOK_CHANNEL
  ).trim().replace(/^@/, '').toLowerCase();
  const allowDisabled = options.allowDisabled === true;

  if (!allowDisabled && (DISABLED_CHANNEL_IDS.has(requestedId) || DISABLED_TIKTOK_CHANNELS.has(requestedName))) {
    return null;
  }

  const account = await gql(`query { account { organizations { id name } } }`);
  const orgs = account?.account?.organizations || [];

  for (const org of orgs) {
    const data = await gql(
      `query GetChannels($organizationId: OrganizationId!) {
        channels(input: { organizationId: $organizationId }) {
          id
          name
          displayName
          service
          isQueuePaused
        }
      }`,
      { organizationId: org.id }
    );

    const channels = (data?.channels || []).filter(c => String(c.service).toLowerCase() === 'tiktok');

    if (requestedId) {
      const exact = channels.find(c => String(c.id) === requestedId);
      if (exact) return { organization: org, channel: exact };
    }

    if (requestedName) {
      const exact = channels.find(c => [c.name, c.displayName]
        .map(v => String(v || '').replace(/^@/, '').toLowerCase())
        .includes(requestedName));
      if (exact) return { organization: org, channel: exact };
    }
  }

  return null;
}

export async function findBufferVideoPostBySource({ channelId, videoUrl, caption = '', allowDisabled = false, first = 60 }) {
  const target = await getBufferTikTokChannel({ channelId, allowDisabled });
  if (!target) return null;

  const data = await gql(
    `query RecentPosts($organizationId: OrganizationId!, $channelId: ChannelId!, $first: Int!) {
      posts(first: $first, input: {
        organizationId: $organizationId,
        filter: { status: [scheduled, sent], channelIds: [$channelId] },
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
          }
        }
      }
    }`,
    {
      organizationId: target.organization.id,
      channelId: target.channel.id,
      first: Math.min(60, Math.max(1, Number(first) || 60))
    }
  );

  const posts = (data?.posts?.edges || []).map(edge => edge.node);
  const wantedIdentity = normalizePostIdentity(caption);

  return posts.find(post => {
    const exactUrl = post?.assets?.some(asset => asset?.source === videoUrl);
    if (exactUrl) return true;

    const priorIdentity = normalizePostIdentity(post?.text || '');
    return wantedIdentity.length >= 8 && priorIdentity === wantedIdentity;
  }) || null;
}

export async function createBufferVideoPost({ channelId, caption, videoUrl, dueAt = null, allowDisabled = false, dedupeVideoUrl = true }) {
  if (!allowDisabled && DISABLED_CHANNEL_IDS.has(String(channelId || '').trim())) {
    throw new Error('Publishing to this TikTok channel is disabled by user request.');
  }

  if (dedupeVideoUrl) {
    const duplicate = await findBufferVideoPostBySource({ channelId, videoUrl, caption, allowDisabled });
    if (duplicate) return { ...duplicate, deduplicated: true };
  }

  const text = await withTrendingHashtags(caption, 3);
  const input = {
    text,
    channelId,
    schedulingType: 'automatic',
    mode: dueAt ? 'customScheduled' : 'addToQueue',
    aiAssisted: false,
    assets: [
      {
        video: {
          url: videoUrl,
          metadata: { thumbnailOffset: 1000 }
        }
      }
    ]
  };

  if (dueAt) input.dueAt = new Date(dueAt).toISOString();

  const data = await gql(
    `mutation CreateVideoPost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post { id text dueAt status }
        }
        ... on MutationError { message }
      }
    }`,
    { input }
  );

  if (data?.createPost?.message) throw new Error(data.createPost.message);
  if (!data?.createPost?.post) throw new Error('Buffer did not return a created post.');
  return data.createPost.post;
}
