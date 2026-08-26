function getAccessToken(req) {
  const cookies = req.headers.cookie || "";

  const match = cookies
    .split(";")
    .map(c => c.trim())
    .find(c => c.startsWith("tiktok_access_token="));

  if (!match) return null;

  return decodeURIComponent(match.split("=")[1]);
}

export default async function handler(req, res) {
  const token = getAccessToken(req);

  if (!token) {
    return res.status(401).json({
      error: {
        code: "not_connected",
        message: "TikTok account is not connected."
      }
    });
  }

  try {
    if (req.method === "GET") {
      const response = await fetch(
        "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json; charset=UTF-8"
          }
        }
      );

      const data = await response.json();

      return res
        .status(response.ok ? 200 : response.status)
        .json(data);
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

      const creatorResponse = await fetch(
        "https://open.tiktokapis.com/v2/post/publish/creator_info/query/",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json; charset=UTF-8"
          }
        }
      );

      const creatorData = await creatorResponse.json();

      if (
        !creatorResponse.ok ||
        creatorData?.error?.code !== "ok"
      ) {
        return res
          .status(creatorResponse.ok ? 400 : creatorResponse.status)
          .json(creatorData);
      }

      const creator = creatorData.data;

      if (
        !creator.privacy_level_options?.includes(privacy_level)
      ) {
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

      const response = await fetch(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json; charset=UTF-8"
          },
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

      const data = await response.json();

      return res
        .status(response.ok ? 200 : response.status)
        .json(data);
    }

    return res.status(405).json({
      error: {
        code: "method_not_allowed",
        message: "Method not allowed."
      }
    });
  } catch (error) {
    console.error(error);

    return res.status(500).json({
      error: {
        code: "server_error",
        message: "TikTok request failed."
      }
    });
  }
}
