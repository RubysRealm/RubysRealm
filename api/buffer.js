const BUFFER_ENDPOINT = "https://api.buffer.com";

async function bufferGraphQL(apiKey, query, variables = {}) {
  const response = await fetch(BUFFER_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`
    },
    body: JSON.stringify({ query, variables })
  });

  const data = await response.json();

  if (!response.ok) {
    const error = new Error(`Buffer request failed with status ${response.status}`);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  if (data.errors?.length) {
    const error = new Error(data.errors.map(e => e.message).join("; "));
    error.status = 400;
    error.data = data;
    throw error;
  }

  return data.data;
}

async function discoverTikTokChannel(apiKey) {
  const accountData = await bufferGraphQL(
    apiKey,
    `query GetOrganizations {
      account {
        organizations {
          id
          name
        }
      }
    }`
  );

  const organizations = accountData?.account?.organizations || [];

  if (!organizations.length) {
    throw new Error("No Buffer organization was found for this API key.");
  }

  const matches = [];

  for (const organization of organizations) {
    const channelData = await bufferGraphQL(
      apiKey,
      `query GetChannels($organizationId: OrganizationId!) {
        channels(input: { organizationId: $organizationId }) {
          id
          name
          displayName
          service
          isQueuePaused
        }
      }`,
      { organizationId: organization.id }
    );

    for (const channel of channelData?.channels || []) {
      if (String(channel.service || "").toLowerCase() === "tiktok") {
        matches.push({
          ...channel,
          organizationId: organization.id,
          organizationName: organization.name
        });
      }
    }
  }

  if (!matches.length) {
    throw new Error("No TikTok channel is connected to this Buffer account.");
  }

  const configuredChannelId = process.env.BUFFER_TIKTOK_CHANNEL_ID;

  if (configuredChannelId) {
    const configured = matches.find(channel => channel.id === configuredChannelId);
    if (!configured) {
      throw new Error("BUFFER_TIKTOK_CHANNEL_ID does not match a connected TikTok channel.");
    }
    return configured;
  }

  if (matches.length > 1) {
    const error = new Error(
      "More than one TikTok channel is connected. Set BUFFER_TIKTOK_CHANNEL_ID to choose the Ruby's Realm channel."
    );
    error.channels = matches.map(channel => ({
      id: channel.id,
      name: channel.name,
      displayName: channel.displayName
    }));
    throw error;
  }

  return matches[0];
}

function validateVideoUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:";
  } catch {
    return false;
  }
}

export default async function handler(req, res) {
  const apiKey = process.env.BUFFER_API_KEY;

  if (!apiKey) {
    return res.status(503).json({
      ok: false,
      error: "BUFFER_API_KEY is not configured on the server."
    });
  }

  try {
    if (req.method === "GET") {
      const channel = await discoverTikTokChannel(apiKey);

      return res.status(200).json({
        ok: true,
        connected: true,
        channel: {
          id: channel.id,
          name: channel.name,
          displayName: channel.displayName,
          service: channel.service,
          isQueuePaused: channel.isQueuePaused,
          organizationId: channel.organizationId,
          organizationName: channel.organizationName
        }
      });
    }

    if (req.method === "POST") {
      const {
        video_url,
        caption = "",
        due_at = null,
        thumbnail_offset_ms = 1000,
        publish_now = false
      } = req.body || {};

      if (!validateVideoUrl(video_url)) {
        return res.status(400).json({
          ok: false,
          error: "video_url must be a publicly accessible HTTPS video URL."
        });
      }

      const channel = await discoverTikTokChannel(apiKey);
      const scheduled = Boolean(due_at);
      const publishNow = Boolean(publish_now);

      if (scheduled && Number.isNaN(Date.parse(due_at))) {
        return res.status(400).json({
          ok: false,
          error: "due_at must be a valid ISO 8601 date-time."
        });
      }

      const input = {
        text: String(caption),
        channelId: channel.id,
        schedulingType: "automatic",
        mode: publishNow ? "shareNow" : (scheduled ? "customScheduled" : "addToQueue"),
        aiAssisted: true,
        assets: [
          {
            video: {
              url: video_url,
              metadata: {
                thumbnailOffset: Math.max(0, Number(thumbnail_offset_ms) || 0)
              }
            }
          }
        ]
      };

      if (scheduled) {
        input.dueAt = new Date(due_at).toISOString();
      }

      const publishData = await bufferGraphQL(
        apiKey,
        `mutation CreateVideoPost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post {
                id
                text
                dueAt
                status
                assets {
                  id
                  mimeType
                  source
                }
              }
            }
            ... on MutationError {
              message
            }
          }
        }`,
        { input }
      );

      const result = publishData?.createPost;

      if (!result?.post) {
        return res.status(400).json({
          ok: false,
          error: result?.message || "Buffer did not create the TikTok post."
        });
      }

      return res.status(200).json({
        ok: true,
        channel: {
          id: channel.id,
          displayName: channel.displayName,
          service: channel.service
        },
        post: result.post
      });
    }

    return res.status(405).json({
      ok: false,
      error: "Method not allowed."
    });
  } catch (error) {
    console.error("Buffer integration error:", error);

    return res.status(error.status || 500).json({
      ok: false,
      error: error.message || "Buffer integration failed.",
      channels: error.channels || undefined
    });
  }
}
