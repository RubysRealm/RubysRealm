export const config = { runtime: 'edge' };

const PREFIX = '/RubysRealm/RubysRealm/releases/download/podcast-part-';

function validSource(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && u.hostname === 'github.com' && u.pathname.startsWith(PREFIX) && u.pathname.toLowerCase().endsWith('.mp4');
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
  const upstream = await fetch(source, { method, redirect: 'follow' });
  if (!upstream.ok) {
    return new Response(`upstream ${upstream.status}`, { status: 502 });
  }

  const headers = new Headers();
  headers.set('content-type', 'video/mp4');
  headers.set('cache-control', 'public, max-age=3600, s-maxage=86400');
  headers.set('accept-ranges', 'bytes');
  const len = upstream.headers.get('content-length');
  if (len) headers.set('content-length', len);

  if (method === 'HEAD') return new Response(null, { status: 200, headers });
  return new Response(upstream.body, { status: 200, headers });
}
