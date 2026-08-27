function getCookies(req) {
  const cookies = req.headers.cookie || "";
  const out = {};
  cookies.split(";").map(v => v.trim()).filter(Boolean).forEach(pair => {
    const i = pair.indexOf("=");
    if (i < 0) return;
    out[pair.slice(0, i)] = decodeURIComponent(pair.slice(i + 1));
  });
  return out;
}

function serializeCookie(name, value, maxAge) {
  return `${name}=${encodeURIComponent(value)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${Math.max(0, Number(maxAge) || 0)}`;
}

function setAuthCookies(res, data) {
  const cookies = [];
  if (data.access_token) cookies.push(serializeCookie("tiktok_access_token", data.access_token, data.expires_in || 86400));
  if (data.refresh_token) cookies.push(serializeCookie("tiktok_refresh_token", data.refresh_token, data.refresh_expires_in || 31536000));
  if (cookies.length) res.setHeader("Set-Cookie", cookies);
}

async function refreshAccessToken(refreshToken) {
  const body = new URLSearchParams({
    client_key: process.env.TIKTOK_CLIENT_KEY,
    client_secret: process.env.TIKTOK_CLIENT_SECRET,
    grant_type: "refresh_token",
    refresh_token: refreshToken
  });

  const response = await fetch("https://open.tiktokapis.com/v2/oauth/token/", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString()
  });
  const data = await response.json();
  if (!response.ok || !data.access_token) throw new Error(data?.error_description || data?.error?.message || "TikTok session refresh failed.");
  return data;
}

async function getAccessToken(req, res) {
  const cookies = getCookies(req);
  let accessToken = cookies.tiktok_access_token || null;
  let refreshToken = cookies.tiktok_refresh_token || null;
  if (!accessToken && refreshToken) {
    const refreshed = await refreshAccessToken(refreshToken);
    setAuthCookies(res, refreshed);
    accessToken = refreshed.access_token;
  }
  if (!accessToken) throw new Error("TikTok account is not connected in this browser.");
  return { accessToken, refreshToken };
}

async function tiktok(accessToken, url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json; charset=UTF-8"
    }
  });
  const data = await response.json();
  return { response, data };
}

async function withRefresh(req, res, url, options = {}) {
  let { accessToken, refreshToken } = await getAccessToken(req, res);
  let result = await tiktok(accessToken, url, options);
  if (result.response.status === 401 && refreshToken) {
    const refreshed = await refreshAccessToken(refreshToken);
    setAuthCookies(res, refreshed);
    accessToken = refreshed.access_token;
    result = await tiktok(accessToken, url, options);
  }
  return { ...result, accessToken };
}

function allowedVideoUrl(raw) {
  try {
    const u = new URL(raw);
    return u.protocol === "https:" && ["files2.heygen.ai", "resource2.heygen.ai"].includes(u.hostname);
  } catch {
    return false;
  }
}

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ error: "Method not allowed" });

  try {
    const { video_url, caption = "" } = req.body || {};
    if (!allowedVideoUrl(video_url)) return res.status(400).json({ error: "Unsupported video source." });

    const source = await fetch(video_url);
    if (!source.ok) return res.status(502).json({ error: "Could not load finished video." });
    const video = Buffer.from(await source.arrayBuffer());
    const size = video.length;
    if (!size) return res.status(502).json({ error: "Finished video was empty." });

    const creatorResult = await withRefresh(req, res, "https://open.tiktokapis.com/v2/post/publish/creator_info/query/", { method: "POST" });
    if (!creatorResult.response.ok || creatorResult.data?.error?.code !== "ok") {
      return res.status(creatorResult.response.status || 400).json(creatorResult.data);
    }

    const creator = creatorResult.data.data;
    if (!creator.privacy_level_options?.includes("PUBLIC_TO_EVERYONE")) {
      return res.status(409).json({ error: "Public Direct Post is not currently available for this TikTok connection." });
    }

    const init = await tiktok(creatorResult.accessToken, "https://open.tiktokapis.com/v2/post/publish/video/init/", {
      method: "POST",
      body: JSON.stringify({
        post_info: {
          title: caption,
          privacy_level: "PUBLIC_TO_EVERYONE",
          disable_comment: Boolean(creator.comment_disabled),
          disable_duet: true,
          disable_stitch: true,
          brand_content_toggle: false,
          brand_organic_toggle: false,
          is_aigc: true
        },
        source_info: {
          source: "FILE_UPLOAD",
          video_size: size,
          chunk_size: size,
          total_chunk_count: 1
        }
      })
    });

    if (!init.response.ok || init.data?.error?.code !== "ok") {
      return res.status(init.response.status || 400).json(init.data);
    }

    const uploadUrl = init.data.data.upload_url;
    const uploaded = await fetch(uploadUrl, {
      method: "PUT",
      headers: {
        "Content-Type": "video/mp4",
        "Content-Length": String(size),
        "Content-Range": `bytes 0-${size - 1}/${size}`
      },
      body: video
    });

    if (!uploaded.ok) return res.status(502).json({ error: "TikTok upload failed." });

    return res.status(200).json({ ok: true, publish_id: init.data.data.publish_id });
  } catch (error) {
    console.error(error);
    return res.status(500).json({ error: error.message || "Posting failed." });
  }
}
