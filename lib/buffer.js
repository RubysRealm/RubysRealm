const BUFFER_ENDPOINT = 'https://api.buffer.com';
const LEGACY_TIKTOK_CHANNEL = 'takurada';

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

  const data = await response.json();
  if (!response.ok) throw new Error(`Buffer HTTP ${response.status}`);
  if (data.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
  return data.data;
}

export async function getBufferTikTokChannel(options = {}) {
  const requestedId = String(options.channelId || '').trim();
  const requestedName = String(
    options.channelName || process.env.BUFFER_TIKTOK_CHANNEL_NAME || LEGACY_TIKTOK_CHANNEL
  ).trim().replace(/^@/, '').toLowerCase();

  if (requestedName === 'rubaradaclips' && process.env.RUBYCLIPS_PUBLISH_ENABLED !== '1') {
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

export async function createBufferVideoPost({ channelId, caption, videoUrl, dueAt = null }) {
  const input = {
    text: String(caption || ''),
    channelId,
    schedulingType: 'automatic',
    mode: dueAt ? 'customScheduled' : 'addToQueue',
    aiAssisted: true,
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
