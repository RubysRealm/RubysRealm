export default function handler(req, res) {
  if (req.method !== "GET") return res.status(405).json({ ok: false });
  return res.status(200).json({
    ok: true,
    publishing: {
      buffer: Boolean(process.env.BUFFER_API_KEY),
      tiktokChannelConfigured: Boolean(process.env.BUFFER_TIKTOK_CHANNEL_ID)
    },
    generation: {
      heygen: Boolean(process.env.HEYGEN_API_KEY),
      runway: Boolean(process.env.RUNWAY_API_KEY),
      higgsfield: Boolean(process.env.HIGGSFIELD_API_KEY),
      openai: Boolean(process.env.OPENAI_API_KEY),
      vercelAiGateway: Boolean(process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN),
      builtInAnimatedRenderer: true
    },
    storage: {
      vercelBlob: Boolean(process.env.BLOB_READ_WRITE_TOKEN)
    },
    cron: Boolean(process.env.CRON_SECRET),
    activeFormat: "animated-story-v2"
  });
}
