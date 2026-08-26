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
      error: "TikTok account is not connected."
    });
  }

  try {

    // Get creator information
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

      return res.status(response.ok ? 200 : 400).json(data);
    }

    // Initialize video post
    if (req.method === "POST") {
      const {
        title,
        video_size,
        privacy_level = "SELF_ONLY"
      } = req.body;

      if (!video_size) {
        return res.status(400).json({
          error: "Missing video size."
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
              title: title || "",
              privacy_level,
              disable_duet: false,
              disable_comment: false,
              disable_stitch: false,
              is_aigc: true
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

      return res.status(response.ok ? 200 : 400).json(data);
    }

    return res.status(405).json({
      error: "Method not allowed."
    });

  } catch (error) {
    console.error(error);

    return res.status(500).json({
      error: "TikTok posting request failed."
    });
  }
}
