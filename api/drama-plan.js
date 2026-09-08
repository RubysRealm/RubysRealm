import { createDramaEpisode, previewDramaEpisode } from '../content/drama-engine.js';

export default async function handler(req, res) {
  if (!['GET', 'HEAD'].includes(req.method)) return res.status(405).end();
  const seed = String(req.query?.seed || new Date().toISOString().slice(0, 10));
  const episode = Math.min(8, Math.max(1, Number(req.query?.episode) || 1));
  if (req.method === 'HEAD') {
    const p = previewDramaEpisode(seed, episode);
    res.setHeader('X-Drama-Series', encodeURIComponent(p.seriesTitle));
    res.setHeader('X-Drama-Episode', String(p.episodeNumber));
    res.setHeader('X-AI-Generated', 'true');
    return res.status(200).end();
  }
  const plan = await createDramaEpisode(seed, episode);
  return res.status(200).json(plan);
}
