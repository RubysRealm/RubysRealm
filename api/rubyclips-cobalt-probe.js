export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });

  const api = 'https://rubyclips-cobalt-3.onrender.com/';
  const video = 'https://www.youtube.com/watch?v=5-bO9NAhWbI';

  try {
    const rootResponse = await fetch(api, { redirect: 'follow', cache: 'no-store' });
    const rootText = await rootResponse.text();
    let root = null;
    try { root = JSON.parse(rootText); } catch { root = { raw: rootText.slice(0, 1000) }; }

    const response = await fetch(api, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        url: video,
        videoQuality: '720',
        youtubeVideoCodec: 'h264',
        downloadMode: 'auto',
        alwaysProxy: true
      }),
      redirect: 'follow',
      cache: 'no-store'
    });

    const text = await response.text();
    let resolved = null;
    try { resolved = JSON.parse(text); } catch { resolved = { raw: text.slice(0, 4000) }; }

    let media = null;
    if (resolved?.url && /^https?:\/\//i.test(resolved.url)) {
      try {
        const probe = await fetch(resolved.url, {
          headers: { Range: 'bytes=0-262143' },
          redirect: 'follow',
          cache: 'no-store'
        });
        const bytes = new Uint8Array(await probe.arrayBuffer());
        media = {
          ok: probe.ok || probe.status === 206,
          status: probe.status,
          contentType: probe.headers.get('content-type'),
          contentRange: probe.headers.get('content-range'),
          contentLength: probe.headers.get('content-length'),
          sampleBytes: bytes.byteLength,
          signature: Array.from(bytes.slice(0, 16))
        };
      } catch (error) {
        media = { ok: false, error: error.message };
      }
    }

    return res.status(200).json({
      ok: response.ok && ['tunnel', 'redirect'].includes(resolved?.status) && media?.ok,
      apiStatus: rootResponse.status,
      root,
      resolveStatus: response.status,
      resolved,
      media
    });
  } catch (error) {
    return res.status(500).json({ ok: false, error: error.message });
  }
}
