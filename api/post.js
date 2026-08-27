function getCookies(req) {
  const cookies = req.headers.cookie || "";
  const result = {};

  cookies
    .split(";")
    .map(c => c.trim())
    .filter(Boolean)
    .forEach(c => {
      const index = c.indexOf("=");
      if (index === -1) return;
      const key = c.slice(0, index);
      const value = c.slice(index + 1);
      result[key] = decodeURIComponent(value);
    });

  return result;
}

function serializeCookie(name, value, maxAge) {
  return `${name}=${encodeURIComponent(value)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${Math.max(0, Number(maxAge) || 0)}`;
}

function setAuthCookies(res, data) {
  const cookies = [];

  if (data.access_token) {
    cookies.push(
      serializeCookie(
        "tiktok_access_token",
        data.access_token,
        data.expires_in || 86400
      )
    );
  }

  if (data.refresh_token) {
    cookies.push(
      serializeCookie(
        "tiktok_refresh_token",
        data.refresh_token,
        data.refresh_expires_in || 31536000
      )
    );
  }

  if (cookies.length) {
    res.setHeader("Set-Cookie", cookies);
  }
}

async function refreshAccessToken(refreshToken) {
  const body = new URLSearchParams({
    client_key: process.env.TIKTOK_CLIENT_KEY,
    client_secret: process.env.TIKTOK_CLIENT_SECRET,
    grant_type: "refresh_token",
    refresh_token: refreshToken
  });

  const response = await fetch(
    "https://open.tiktokapis.com/v2/oauth/token/",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: body.toString()
    }
  );

  const data = await response.json();

  if (!response.ok || !data.access_token) {
    const error = new Error(
      data?.error_description ||
      data?.error?.message ||
      "TikTok session refresh failed."
    );
    error.status = response.status || 401;
    throw error;
  }

  return data;
}

async function getAuth(req, res) {
  const cookies = getCookies(req);
  let accessToken = cookies.tiktok_access_token || null;
  let refreshToken = cookies.tiktok_refresh_token || null;

  if (!accessToken && refreshToken) {
    const refreshed = await refreshAccessToken(refreshToken);
    setAuthCookies(res, refreshed);
    accessToken = refreshed.access_token;
    refreshToken = refreshed.refresh_token || refreshToken;
  }

  return { accessToken, refreshToken };
}

async function tiktokRequest(accessToken, url, options = {}) {
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

async function requestWithRefresh(req, res, url, options = {}) {
  let { accessToken, refreshToken } = await getAuth(req, res);

  if (!accessToken) {
    return {
      response: null,
      data: {
        error: {
          code: "not_connected",
          message: "TikTok account is not connected."
        }
      },
      accessToken: null
    };
  }

  let result = await tiktokRequest(accessToken, url, options);

  if (result.response.status === 401 && refreshToken) {
    const refreshed = await refreshAccessToken(refreshToken);
    setAuthCookies(res, refreshed);
    accessToken = refreshed.access_token;
    result = await tiktokRequest(accessToken, url, options);
  }

  return {
    ...result,
    accessToken
  };
}

export default async function handler(req, res) {
  try {
    if (req.method === "GET") {
      const creatorResult = await requestWithRefresh(
        req,
        res,
        "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
        { method: "POST" }
      );

      if (!creatorResult.response) {
        return res.status(401).json(creatorResult.data);
      }

      return res
        .status(creatorResult.response.ok ? 200 : creatorResult.response.status)
        .json(creatorResult.data);
    }

    if (req.method === "POST") {
      const {
        title = "",
        privacy_level,
        allow_comment = false,
        allow_duet = false,
        allow_stitch = false,
        commercial_content = false,
        your_brand = false,
        branded_content = false,
        is_aigc = false,
        video_size
      } = req.body || {};

      if (!privacy_level) {
        return res.status(400).json({
          error: {
            code: "privacy_required",
            message: "Choose a privacy setting."
          }
        });
      }

      if (!video_size || Number(video_size) <= 0) {
        return res.status(400).json({
          error: {
            code: "video_required",
            message: "Missing video information."
          }
        });
      }

      if (commercial_content && !your_brand && !branded_content) {
        return res.status(400).json({
          error: {
            code: "commercial_selection_required",
            message: "Select Your Brand, Branded Content, or both."
          }
        });
      }

      const creatorResult = await requestWithRefresh(
        req,
        res,
        "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
        { method: "POST" }
      );

      if (!creatorResult.response) {
        return res.status(401).json(creatorResult.data);
      }

      const creatorData = creatorResult.data;

      if (
        !creatorResult.response.ok ||
        creatorData?.error?.code !== "ok"
      ) {
        return res
          .status(
            creatorResult.response.ok
              ? 400
              : creatorResult.response.status
          )
          .json(creatorData);
      }

      const creator = creatorData.data;

      if (!creator.privacy_level_options?.includes(privacy_level)) {
        return res.status(400).json({
          error: {
            code: "privacy_level_option_mismatch",
            message:
              "The selected privacy level is not available for this TikTok account."
          }
        });
      }

      if (branded_content && privacy_level === "SELF_ONLY") {
        return res.status(400).json({
          error: {
            code: "branded_content_private",
            message:
              "Branded Content cannot be posted with Only Me visibility."
          }
        });
      }

      const publishResult = await tiktokRequest(
        creatorResult.accessToken,
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        {
          method: "POST",
          body: JSON.stringify({
            post_info: {
              title,
              privacy_level,
              disable_comment:
                creator.comment_disabled || !allow_comment,
              disable_duet:
                creator.duet_disabled || !allow_duet,
              disable_stitch:
                creator.stitch_disabled || !allow_stitch,
              brand_content_toggle:
                commercial_content && branded_content,
              brand_organic_toggle:
                commercial_content && your_brand,
              is_aigc: Boolean(is_aigc)
            },
            source_info: {
              source: "FILE_UPLOAD",
              video_size: Number(video_size),
              chunk_size: Number(video_size),
              total_chunk_count: 1
            }
          })
        }
      );

      return res
        .status(publishResult.response.ok ? 200 : publishResult.response.status)
        .json(publishResult.data);
    }

    return res.status(405).json({
      error: {
        code: "method_not_allowed",
        message: "Method not allowed."
      }
    });
  } catch (error) {
    console.error(error);

    return res.status(error.status || 500).json({
      error: {
        code:
          error.status === 401
            ? "session_refresh_failed"
            : "server_error",
        message:
          error.message ||
          "TikTok request failed."
      }
    });
  }
}
