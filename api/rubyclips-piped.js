const PIPED_APIS = [
  'https://pipedapi.wireway.ch',
  'https://pipedapi.r4fo.com',
  'https://pipedapi.qdi.fi'
];

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ ok: false, error: 'Method not allowed' });
  }

  const video = String(req.query?.video || '').trim();
  if (!/^[A-Za-z0-9_-]{11}$/.test(video)) {
    return res.status(400).json({ ok: false, error: 'Valid YouTube video id required' });
  }

  const errors = [];
  for (const base of PIPED_APIS) {
    try {
      const response = await fetch(`${base}/streams/${encodeURIComponent(video)}`, {
        headers: {
          Accept: 'application/json',
          'User-Agent': 'Mozilla/5.0 (compatible; Rubaradaclips/1.0)'
        },
        redirect: 'follow',
        cache: 'no-store'
      });

      if (!response.ok) {
        errors.push(`${base}: HTTP ${response.status}`);
        continue;
      }

      const data = await response.json();
      const hls = String(data?.hls || '');
      const duration = Number(data?.duration || 0);
      if (/^https:\/\//i.test(hls) && duration > 15) {
        res.setHeader('Cache-Control', 'no-store');
        return res.status(200).json({
          ok: true,
          video,
          hls,
          duration,
          source: base,
          title: String(data?.title || ''),
          uploader: String(data?.uploader || '')
        });
      }

      errors.push(`${base}: missing HLS/duration`);
    } catch (error) {
      errors.push(`${base}: ${String(error?.message || error).slice(0, 300)}`);
    }
  }

  return res.status(502).json({ ok: false, video, error: 'No Piped source available', details: errors });
}
