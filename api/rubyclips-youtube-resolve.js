import { Innertube, UniversalCache } from 'youtubei.js';

const ALLOWED_VIDEO_ID = '5-bO9NAhWbI';
const ALLOWED_CHANNEL = '@muffindrama-uvu';

function safeFormat(format, strategy) {
  if (!format) return null;
  return {
    strategy,
    itag: Number(format.itag || 0) || null,
    mimeType: format.mime_type || null,
    quality: format.quality_label || format.quality || null,
    width: Number(format.width || 0) || null,
    height: Number(format.height || 0) || null,
    fps: Number(format.fps || 0) || null,
    bitrate: Number(format.bitrate || 0) || null,
    contentLength: Number(format.content_length || 0) || null,
    hasAudio: format.has_audio === true,
    hasVideo: format.has_video === true,
    url: format.url || null
  };
}

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok: false, error: 'Method not allowed' });

  const id = String(req.query?.id || ALLOWED_VIDEO_ID).trim();
  if (id !== ALLOWED_VIDEO_ID) return res.status(403).json({ ok: false, error: 'Video id is not allowed for this Rubaradaclips resolver.' });

  try {
    const youtube = await Innertube.create({
      cache: new UniversalCache(false),
      generate_session_locally: true,
      retrieve_player: true
    });

    const attempts = [
      ['itag18-ios', { itag: 18, client: 'IOS' }],
      ['itag18-android', { itag: 18, client: 'ANDROID' }],
      ['itag18-tv-embedded', { itag: 18, client: 'TV_EMBEDDED' }],
      ['muxed-720-ios', { type: 'video+audio', quality: '720p', format: 'mp4', client: 'IOS' }],
      ['muxed-360-ios', { type: 'video+audio', quality: '360p', format: 'mp4', client: 'IOS' }],
      ['muxed-best-android', { type: 'video+audio', quality: 'best', format: 'mp4', client: 'ANDROID' }]
    ];

    const errors = [];
    for (const [name, options] of attempts) {
      try {
        const format = await youtube.getStreamingData(id, options);
        let url = format?.url || '';
        if (!url && typeof format?.decipher === 'function') {
          try { url = await format.decipher(youtube.session?.player); } catch {}
        }
        const info = safeFormat(format, name);
        if (url && /^https:\/\//i.test(url)) {
          return res.status(200).json({
            ok: true,
            sourceProvider: 'youtube',
            sourceChannel: ALLOWED_CHANNEL,
            videoId: id,
            ...info,
            url
          });
        }
        errors.push(`${name}: no usable URL`);
      } catch (error) {
        errors.push(`${name}: ${String(error?.message || error).slice(0, 300)}`);
      }
    }

    return res.status(502).json({ ok: false, videoId: id, error: 'No usable stream returned.', attempts: errors });
  } catch (error) {
    console.error('rubyclips-youtube-resolve failed', error);
    return res.status(500).json({ ok: false, videoId: id, error: String(error?.message || error) });
  }
}
