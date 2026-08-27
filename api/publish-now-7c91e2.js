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

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });
  try {
    const data = await gql(
      `mutation EditPost($input: EditPostInput!) {
        editPost(input: $input) {
          ... on PostActionSuccess {
            post { id text status dueAt sentAt externalLink }
          }
          ... on MutationError { message }
        }
      }`,
      { input: { id: '6a90af00479d79c4496130a6', mode: 'shareNow', schedulingType: 'automatic' } }
    );

    const result = data?.editPost;
    if (!result?.post) return res.status(400).json({ ok: false, error: result?.message || 'Buffer did not publish the post.' });
    return res.status(200).json({ ok: true, post: result.post });
  } catch (error) {
    console.error(error);
    return res.status(500).json({ ok: false, error: error.message || 'Publish failed' });
  }
}
