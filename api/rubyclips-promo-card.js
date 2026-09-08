import sharp from 'sharp';

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).end();

  const title = String(req.query?.title || 'Building a Warm and Cozy forest House').slice(0, 120);
  const part = String(req.query?.part || 'Part 1/2').slice(0, 40);
  const handle = String(req.query?.handle || '@rubaradaclips').slice(0, 40);

  const esc = (s) => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
  const words = title.split(/\s+/);
  const lines = [];
  let current = '';
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > 24 && current) { lines.push(current); current = word; }
    else current = next;
  }
  if (current) lines.push(current);
  const clipped = lines.slice(0, 4);

  const titleSvg = clipped.map((line, i) =>
    `<text x="540" y="${560 + i * 92}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="74" font-weight="800" fill="#ffffff">${esc(line)}</text>`
  ).join('');

  const svg = `
  <svg width="1080" height="1920" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#18351f"/>
        <stop offset="0.55" stop-color="#31573a"/>
        <stop offset="1" stop-color="#101812"/>
      </linearGradient>
      <filter id="shadow"><feDropShadow dx="0" dy="8" stdDeviation="12" flood-opacity="0.45"/></filter>
    </defs>
    <rect width="1080" height="1920" fill="url(#g)"/>
    <circle cx="145" cy="180" r="72" fill="#ffffff" opacity="0.08"/>
    <circle cx="925" cy="320" r="120" fill="#ffffff" opacity="0.05"/>
    <rect x="100" y="375" width="880" height="720" rx="42" fill="#000000" opacity="0.28" filter="url(#shadow)"/>
    <text x="540" y="470" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="54" font-weight="700" fill="#b8e2c1">RUBYCLIPS</text>
    ${titleSvg}
    <rect x="330" y="980" width="420" height="120" rx="28" fill="#000000" opacity="0.72"/>
    <text x="540" y="1060" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="66" font-weight="800" fill="#ffffff">${esc(part)}</text>
    <text x="540" y="1285" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="58" font-weight="700" fill="#ffffff">WATCH NOW</text>
    <text x="540" y="1380" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="52" font-weight="700" fill="#b8e2c1">${esc(handle)}</text>
    <text x="540" y="1660" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="38" fill="#ffffff" opacity="0.82">New parts posted automatically</text>
  </svg>`;

  const jpeg = await sharp(Buffer.from(svg)).jpeg({ quality: 92, chromaSubsampling: '4:4:4' }).toBuffer();
  res.setHeader('Content-Type', 'image/jpeg');
  res.setHeader('Cache-Control', 'public, max-age=3600');
  res.status(200).send(jpeg);
}
