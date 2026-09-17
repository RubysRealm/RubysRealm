const BUFFER_ENDPOINT = 'https://api.buffer.com';
const TARGET_POST_ID = '6aab6eb5b6213d08e064777b';
const TARGET_CHANNEL_ID = '6a9f6ff1cd8b9c702c2897e1';

async function gql(query, variables = {}) {
  const apiKey = process.env.BUFFER_API_KEY;
  if (!apiKey) throw new Error('BUFFER_API_KEY is not configured.');
  const response = await fetch(BUFFER_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({ query, variables })
  });
  const data = await response.json();
  if (!response.ok || data?.errors?.length) throw new Error(data?.errors?.map(e => e.message).join('; ') || `Buffer HTTP ${response.status}`);
  return data?.data;
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false });
  try {
    const data = await gql(`query GetPost($id: PostId!) { post(input: { id: $id }) { id text status channel { id name displayName service } error { message } } }`, { id: TARGET_POST_ID });
    const post = data?.post;
    if (!post) return res.status(404).json({ ok: false, message: 'Target post not found.' });
    const exact = post.id === TARGET_POST_ID && String(post?.channel?.id || '') === TARGET_CHANNEL_ID && String(post?.text || '').includes('The Road Through Fire') && String(post?.text || '').includes('Part 1 of 6');
    if (!exact) return res.status(403).json({ ok: false, message: 'Exact duplicate guard failed.', post });
    if (String(post.status).toLowerCase() === 'sent') return res.status(409).json({ ok: false, alreadySent: true, post });
    const deletedData = await gql(`mutation DeletePost($input: DeletePostInput!) { deletePost(input: $input) { ... on DeletePostSuccess { id } ... on VoidMutationError { message } } }`, { input: { id: TARGET_POST_ID } });
    const deleted = deletedData?.deletePost;
    if (deleted?.message || deleted?.id !== TARGET_POST_ID) throw new Error(deleted?.message || 'Buffer did not confirm exact duplicate deletion.');
    return res.status(200).json({ ok: true, deleted: true, id: TARGET_POST_ID, previousStatus: post.status });
  } catch (error) {
    return res.status(500).json({ ok: false, error: String(error?.message || error) });
  }
}
