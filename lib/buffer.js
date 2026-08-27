const BUFFER_ENDPOINT = 'https://api.buffer.com';

async function gql(query) {
  const apiKey = process.env.BUFFER_API_KEY;
  if (!apiKey) throw new Error('BUFFER_API_KEY is not configured.');

  const response = await fetch(BUFFER_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`
    },
    body: JSON.stringify({ query })
  });

  const data = await response.json();
  if (!response.ok) throw new Error(`Buffer HTTP ${response.status}`);
  if (data.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
  return data.data;
}

export async function getBufferTikTokChannel() {
  const account = await gql(`query { account { organizations { id name } } }`);
  const orgs = account?.account?.organizations || [];

  for (const org of orgs) {
    const data = await gql(`query { channels(input: { organizationId: \"${org.id}\" }) { id name service } }`);
    const channel = (data?.channels || []).find(c => String(c.service).toLowerCase() === 'tiktok');
    if (channel) return { organization: org, channel };
  }

  return null;
}

export async function createBufferVideoPost({ channelId, caption, videoUrl }) {
  const safeCaption = JSON.stringify(caption || '');
  const safeChannel = JSON.stringify(channelId);
  const safeUrl = JSON.stringify(videoUrl);

  const data = await gql(`
    mutation {
      createPost(input: {
        text: ${safeCaption}
        channelId: ${safeChannel}
        schedulingType: automatic
        mode: addToQueue
        aiAssisted: true
        assets: [{ video: { url: ${safeUrl}, metadata: { thumbnailOffset: 1000 } } }]
      }) {
        ... on PostActionSuccess {
          post { id text dueAt status }
        }
        ... on MutationError { message }
      }
    }
  `);

  if (data?.createPost?.message) throw new Error(data.createPost.message);
  if (!data?.createPost?.post) throw new Error('Buffer did not return a created post.');
  return data.createPost.post;
}
