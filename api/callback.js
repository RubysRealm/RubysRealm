function serializeCookie(name, value, maxAge) {
  return `${name}=${encodeURIComponent(value)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${Math.max(0, Number(maxAge) || 0)}`;
}

export default async function handler(req, res) {
  const { code, error, error_description } = req.query;

  if (error) {
    return res.status(400).send(
      `TikTok connection failed: ${error_description || error}`
    );
  }

  if (!code) {
    return res.status(400).send("Missing TikTok authorization code.");
  }

  try {
    const redirectUri =
      "https://rubys-realm.vercel.app/api/callback";

    const body = new URLSearchParams({
      client_key: process.env.TIKTOK_CLIENT_KEY,
      client_secret: process.env.TIKTOK_CLIENT_SECRET,
      code,
      grant_type: "authorization_code",
      redirect_uri: redirectUri
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
      console.error("TikTok OAuth error:", data);
      return res.status(400).send(
        "TikTok authorization failed. Please reconnect the account."
      );
    }

    const cookies = [
      serializeCookie(
        "tiktok_access_token",
        data.access_token,
        data.expires_in || 86400
      )
    ];

    if (data.refresh_token) {
      cookies.push(
        serializeCookie(
          "tiktok_refresh_token",
          data.refresh_token,
          data.refresh_expires_in || 31536000
        )
      );
    }

    res.setHeader("Set-Cookie", cookies);

    res.writeHead(302, {
      Location: "/?connected=1"
    });

    return res.end();

  } catch (err) {
    console.error(err);
    return res.status(500).send("TikTok connection failed.");
  }
}
