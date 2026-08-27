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
      text: "POV: you realize the ocean was never empty. 🌊👁️ #deepsea #horror #liminal #aivideo #rubysrealm",
      channelId: channel.id,
      schedulingType: 'automatic',
      mode: 'shareNow',
      aiAssisted: true,
      assets: [
        {
          video: {
            url: "https://d8j0ntlcm91z4.cloudfront.net/user_3IVucXuJl5D3y0NqtFPdYP7zZMV/hf_20260827_220042_e0bd2e4a-1005-48df-b406-bd04d931c9cb.mp4",
            metadata: { thumbnailOffset: 500 }
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
