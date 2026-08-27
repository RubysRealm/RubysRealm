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
  const data = await response.json();
  if (!response.ok) throw new Error(`Buffer HTTP ${response.status}`);
  if (data.errors?.length) throw new Error(data.errors.map(e => e.message).join('; '));
  return data.data;
}

async function getTikTokChannel() {
  const account = await gql(`query { account { organizations { id name } } }`);
  const orgs = account?.account?.organizations || [];
  for (const org of orgs) {
    const data = await gql(
      `query GetChannels($organizationId: OrganizationId!) {
        channels(input: { organizationId: $organizationId }) { id name displayName service }
      }`,
      { organizationId: org.id }
    );
    const channel = (data?.channels || []).find(c => String(c.service).toLowerCase() === 'tiktok');
    if (channel) return channel;
  }
  return null;
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });
  try {
    const channel = await getTikTokChannel();
    if (!channel) return res.status(404).json({ ok: false, error: 'No TikTok channel connected in Buffer.' });

    const input = {
      text: "That one second after work when you finally sit down… and your brain remembers EVERYTHING 😭 #relatable #afterwork #adulting #rubysrealm",
      channelId: channel.id,
      schedulingType: 'automatic',
      mode: 'shareNow',
      aiAssisted: true,
      assets: [
        {
          video: {
            url: "https://resource2.heygen.ai/aws_pacific/avatar_tmp/1592f1dded57439e808601ba8fbe8818/v19532a7a5136405597ae05ad88727b9f/caption_484da3cd2a0c4e56acc2b9aca12d6cef.mp4",
            metadata: { thumbnailOffset: 1000 }
          }
        }
      ]
    };

    const data = await gql(
      `mutation CreatePost($input: CreatePostInput!) {
        createPost(input: $input) {
          ... on PostActionSuccess {
            post { id text status dueAt sentAt externalLink }
          }
          ... on MutationError { message }
        }
      }`,
      { input }
    );

    const result = data?.createPost;
    if (!result?.post) return res.status(400).json({ ok: false, error: result?.message || 'Buffer did not publish the post.' });
    return res.status(200).json({ ok: true, post: result.post });
  } catch (error) {
    console.error(error);
    return res.status(500).json({ ok: false, error: error.message || 'Publish failed' });
  }
}
