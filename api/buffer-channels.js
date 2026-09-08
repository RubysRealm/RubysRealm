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
    const account = await gql(`query { account { organizations { id name } } }`);
    const channels = [];
    for (const organization of account?.account?.organizations || []) {
      const data = await gql(`query GetChannels($organizationId: OrganizationId!) {
        channels(input: { organizationId: $organizationId }) {
          id
          name
          displayName
          service
          isQueuePaused
        }
      }`, { organizationId: organization.id });
      for (const channel of data?.channels || []) {
        if (String(channel.service).toLowerCase() === 'tiktok') channels.push({ organization, channel });
      }
    }
    return res.status(200).json({ ok: true, channels });
  } catch (error) {
    return res.status(500).json({ ok: false, error: error.message });
  }
}
