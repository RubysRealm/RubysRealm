const BUFFER_ENDPOINT = 'https://api.buffer.com';

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
  try { data = await response.json(); } catch { data = null; }

  if (!response.ok) {
    const error = new Error(`Buffer HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  if (data?.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
  return data?.data;
}

export async function getBufferYouTubeChannel(options = {}) {
  const requestedId = String(options.channelId || '').trim();
  const requestedName = String(options.channelName || '').trim().replace(/^@/, '').toLowerCase();

  const account = await gql(`query { account { organizations { id name } } }`);
  for (const organization of account?.account?.organizations || []) {
    const data = await gql(
      `query GetChannels($organizationId: OrganizationId!) {
        channels(input: { organizationId: $organizationId }) {
          id name displayName service isQueuePaused
        }
      }`,
      { organizationId: organization.id }
    );

    const channels = (data?.channels || []).filter(c => String(c.service).toLowerCase() === 'youtube');
    if (requestedId) {
      const exact = channels.find(c => String(c.id) === requestedId);
      if (exact) return { organization, channel: exact };
    }
    if (requestedName) {
      const exact = channels.find(c => [c.name, c.displayName]
        .map(v => String(v || '').replace(/^@/, '').toLowerCase())
        .includes(requestedName));
      if (exact) return { organization, channel: exact };
    }
    if (!requestedId && !requestedName && channels.length === 1) {
      return { organization, channel: channels[0] };
    }
  }
  return null;
}

export async function recentYouTubePosts(target, first = 60) {
  const data = await gql(
    `query RecentPosts($organizationId: OrganizationId!, $channelId: ChannelId!, $first: Int!) {
      posts(first: $first, input: {
        organizationId: $organizationId,
        filter: { status: [scheduled, sent], channelIds: [$channelId] },
        sort: [{ field: createdAt, direction: desc }]
      }) {
        edges {
          node {
            id text status dueAt sentAt externalLink
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
  return (data?.posts?.edges || []).map(edge => edge.node);
}

export async function createBufferYouTubeShort({ channelId, title, description, videoUrl, dueAt = null }) {
  const cleanTitle = String(title || 'Ruby’s Realm').trim().slice(0, 100);
  const cleanDescription = String(description || '').trim().slice(0, 5000);
  if (!cleanTitle) throw new Error('YouTube title is required.');
  if (!videoUrl) throw new Error('YouTube video URL is required.');

  const input = {
    text: cleanDescription,
    channelId,
    schedulingType: 'automatic',
    mode: dueAt ? 'customScheduled' : 'addToQueue',
    aiAssisted: false,
    assets: [{ video: { url: videoUrl } }],
    metadata: {
      youtube: {
        title: cleanTitle,
        categoryId: '1',
        privacy: 'public',
        madeForKids: false,
        embeddable: true,
        notifySubscribers: true,
        isAiGenerated: true
      }
    }
  };
  if (dueAt) input.dueAt = new Date(dueAt).toISOString();

  const data = await gql(
    `mutation CreateYouTubeShort($input: CreatePostInput!) {
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
  if (!data?.createPost?.post) throw new Error('Buffer did not return a created YouTube post.');
  return data.createPost.post;
}
