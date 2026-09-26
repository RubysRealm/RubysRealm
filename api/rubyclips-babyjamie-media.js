export const config = { runtime: 'edge' };

const ALLOWED_VIDEO_IDS = new Set(['jXkBF-MCjEA']);

function extract(html, patterns) {
  for (const pattern of patterns) {
    const m = html.match(pattern);
    if (m?.[1]) return m[1].replace(/\\u0026/g, '&');
  }
  return '';
}

async function playerResponse(videoId, apiKey, clientVersion, visitorData, clientName) {
  const clients = {
    WEB: { clientName: 'WEB', clientVersion },
    WEB_EMBEDDED_PLAYER: { clientName: 'WEB_EMBEDDED_PLAYER', clientVersion, clientScreen: 'EMBED' },
    TVHTML5: { clientName: 'TVHTML5', clientVersion: '7.20250926' }
  };
  const client = { ...(clients[clientName] || clients.WEB) };
  if (visitorData) client.visitorData = visitorData;

  const response = await fetch(`https://www.youtube.com/youtubei/v1/player?key=${encodeURIComponent(apiKey)}&prettyPrint=false`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'accept': 'application/json',
      'origin': 'https://www.youtube.com',
      'referer': `https://www.youtube.com/watch?v=${videoId}`,
      'user-agent': 'Mozilla/5.0 (SMART-TV; LINUX; Tizen 7.0) AppleWebKit/537.36 Chrome/140 Safari/537.36'
    },
    body: JSON.stringify({
      videoId,
      context: { client },
      playbackContext: { contentPlaybackContext: { html5Preference: 'HTML5_PREF_WANTS' } },
      contentCheckOk: true,
      racyCheckOk: true
    }),
    redirect: 'follow'
  });

  const text = await response.text();
  let data = null;
  try { data = JSON.parse(text); } catch {}
  return { ok: response.ok, status: response.status, data, text: text.slice(0, 500) };
}

function pickMuxed(data) {
  const formats = Array.isArray(data?.streamingData?.formats) ? data.streamingData.formats : [];
  const usable = formats
    .filter(x => typeof x?.url === 'string' && /^https?:\/\//.test(x.url) && /video\/mp4/i.test(String(x.mimeType || '')))
    .sort((a, b) => {
      const ah = Number(a.height || 0), bh = Number(b.height || 0);
      const ap = ah > 0 && ah <= 720 ? ah : 0;
      const bp = bh > 0 && bh <= 720 ? bh : 0;
      return bp - ap || Number(b.bitrate || 0) - Number(a.bitrate || 0);
    });
  return usable.find(x => Number(x.height || 0) <= 720) || usable[0] || null;
}

export default async function handler(req) {
  const u = new URL(req.url);
  const videoId = String(u.searchParams.get('v') || '').trim();
  if (!ALLOWED_VIDEO_IDS.has(videoId)) {
    return Response.json({ ok: false, error: 'source not allowed' }, { status: 400 });
  }

  try {
    const watch = await fetch(`https://www.youtube.com/watch?v=${videoId}&hl=en`, {
      headers: {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36',
        'accept-language': 'en-US,en;q=0.9'
      },
      redirect: 'follow',
      cache: 'no-store'
    });
    const html = await watch.text();
    if (!watch.ok || html.length < 10000) {
      return Response.json({ ok: false, error: 'watch page unavailable', status: watch.status }, { status: 502 });
    }

    const apiKey = extract(html, [
      /"INNERTUBE_API_KEY":"([^"]+)"/,
      /"innertubeApiKey":"([^"]+)"/
    ]);
    const clientVersion = extract(html, [
      /"INNERTUBE_CLIENT_VERSION":"([^"]+)"/,
      /"clientVersion":"([^"]+)"/
    ]) || '2.20250926.00.00';
    const visitorData = extract(html, [
      /"VISITOR_DATA":"([^"]+)"/,
      /"visitorData":"([^"]+)"/
    ]);

    if (!apiKey) {
      return Response.json({ ok: false, error: 'missing innertube api key' }, { status: 502 });
    }

    const attempts = [];
    let format = null;
    let chosenClient = '';
    for (const clientName of ['TVHTML5', 'WEB_EMBEDDED_PLAYER', 'WEB']) {
      const p = await playerResponse(videoId, apiKey, clientVersion, visitorData, clientName);
      const status = String(p.data?.playabilityStatus?.status || '');
      const reason = String(p.data?.playabilityStatus?.reason || '');
      const count = Array.isArray(p.data?.streamingData?.formats) ? p.data.streamingData.formats.length : 0;
      attempts.push({ clientName, http: p.status, status, reason: reason.slice(0, 160), formats: count });
      format = pickMuxed(p.data);
      if (format) {
        chosenClient = clientName;
        break;
      }
    }

    if (!format) {
      return Response.json({ ok: false, error: 'no direct muxed stream', attempts }, { status: 502 });
    }

    const range = req.headers.get('range') || '';
    const upstream = await fetch(format.url, {
      method: req.method === 'HEAD' ? 'HEAD' : 'GET',
      headers: range ? { range } : undefined,
      redirect: 'follow',
      cache: 'no-store'
    });

    if (!upstream.ok && upstream.status !== 206) {
      return Response.json({ ok: false, error: 'media upstream failed', status: upstream.status, client: chosenClient }, { status: 502 });
    }

    const headers = new Headers();
    headers.set('content-type', upstream.headers.get('content-type') || 'video/mp4');
    headers.set('accept-ranges', upstream.headers.get('accept-ranges') || 'bytes');
    headers.set('cache-control', 'no-store');
    headers.set('x-rubyclips-source', `vercel-youtube-${chosenClient.toLowerCase()}`);
    for (const h of ['content-length', 'content-range', 'etag', 'last-modified']) {
      const v = upstream.headers.get(h);
      if (v) headers.set(h, v);
    }

    if (req.method === 'HEAD') return new Response(null, { status: upstream.status, headers });
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch (error) {
    return Response.json({ ok: false, error: String(error?.message || error) }, { status: 500 });
  }
}
