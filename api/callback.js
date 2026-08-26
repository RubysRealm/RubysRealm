export default async function handler(req, res) {
  const { code } = req.query;

  if (!code) {
    return res.status(400).send("Missing TikTok authorization code.");
  }

  try {
    const redirectUri = "https://rubys-realm.vercel.app/api/callback";

    const body = new URLSearchParams({
      client_key: process.env.TIKTOK_CLIENT_KEY,
      client_secret: process.env.TIKTOK_CLIENT_SECRET,
      code: code,
      grant_type: "authorization_code",
      redirect_uri: redirectUri,
    });

    const response = await fetch(
      "https://open.tiktokapis.com/v2/oauth/token/",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: body.toString(),
      }
    );

    const data = await response.json();

    if (!response.ok || data.error) {
      console.error("TikTok token error:", data);
      return res.status(400).json({
        success: false,
        error: data,
      });
    }

    return res.status(200).send(`
      <html>
        <body style="background:#111;color:white;font-family:Arial;text-align:center;padding:60px 20px;">
          <h1>TikTok Connected ✓</h1>
          <p>RubysRealm successfully connected to your TikTok account.</p>
          <p>You can close this page.</p>
        </body>
      </html>
    `);
  } catch (error) {
    console.error(error);
    return res.status(500).json({
      success: false,
      error: "TikTok connection failed.",
    });
  }
}
