export const config = { runtime: 'edge' };

const ALLOWED_PREFIXES = [
  '/RubysRealm/RubysRealm/releases/download/podcast-part-',
  '/RubysRealm/RubysRealm/releases/download/rubyclips-fb-'
];

function validSource(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' &&
      u.hostname === 'github.com' &&
      ALLOWED_PREFIXES.some(prefix => u.pathname.startsWith(prefix)) &&
      u.pathname.toLowerCase().endsWith('.mp4');
  } catch {
    return false;
  }
}

export default async function handler(req) {
  const requestUrl = new URL(req.url);
  const source = requestUrl.searchParams.get('url') || '';
  if (!validSource(source)) {
    return new Response('invalid source', { status: 400 });
  }

  const method = req.method === 'HEAD' ? 'HEAD' : 'GET';
  const upstream = await fetch(source, {
    method,
    redirect: 'follow',
    headers: req.headers.get('range') ? { range: req.headers.get('range') } : undefined
  });
  if (!upstream.ok && upstream.status !== 206) {
    return new Response(`upstream ${upstream.status}`, { status: 502 });
  }

  const headers = new Headers();
  headers.set('content-type', 'video/mp4');
  headers.set('cache-control', 'public, max-age=3600, s-maxage=86400');
  headers.set('accept-ranges', 'bytes');
  const len = upstream.headers.get('content-length');
  const range = upstream.headers.get('content-range');
  if (len) headers.set('content-length', len);
  if (range) headers.set('content-range', range);

  if (method === 'HEAD') return new Response(null, { status: upstream.status === 206 ? 206 : 200, headers });
  return new Response(upstream.body, { status: upstream.status === 206 ? 206 : 200, headers });
}
