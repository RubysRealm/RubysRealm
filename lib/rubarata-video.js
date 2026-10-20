// Account and original-media checks for Rubarata's active His Story queue.
import { createHash } from 'node:crypto';

export const RUBARATA_CHANNEL_ID = '6a9f6ff1cd8b9c702c2897e1';
export const RUBARATA_CHANNEL = 'rubaradaclips';
export const SPOTIFY_SHOW_ID = '6alyG1Jw4KH03mXZlYtPkf';
export const SPOTIFY_FEED = 'https://anchor.fm/s/10ff75318/podcast/rss';
export const PUBLISHER_VERSION = 'hisstory-v17-durable-video';

export function parseReleaseTag(tag) {
  const match = /^rubyclips-tt-(hisstory-[a-f0-9]{16})-r16-p([1-9][0-9]*)$/.exec(String(tag || ''));
  if (!match) throw new Error('A current Rubarata His Story video release tag is required.');
  return { seriesId: match[1], part: Number(match[2]) };
}
function requireValue(condition, message) {
  if (!condition) throw new Error(`Blocked: ${message}`);
}
function finitePositive(value) {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

export function validateSpotifyVideoManifest(m, tag, { forPublish = true } = {}) {
  const { seriesId, part } = parseReleaseTag(tag);
  requireValue(m?.platform === 'rubyclips-tiktok-story-v1' && m?.sourceProvider === 'hisstory-spotify-rss', 'the retired artwork/audio and other source pipelines cannot publish.');
  requireValue(m.spotifyShowId === SPOTIFY_SHOW_ID, 'the Spotify show does not match the requested source.');
  requireValue(m.targetChannel === RUBARATA_CHANNEL, 'the TikTok account does not match Rubarata.');
  requireValue(/^[a-f0-9-]{36}$/.test(m.sourceEpisodeGuid || ''), 'the Spotify feed episode identity is missing.');
  const expectedSeries = 'hisstory-' + createHash('sha256').update(m.sourceEpisodeGuid).digest('hex').slice(0, 16);
  requireValue(m.sourceSeriesId === seriesId && seriesId === expectedSeries, 'the Spotify episode and release disagree.');
  requireValue(m.restartGeneration === 16, 'the video belongs to an obsolete source generation.');
  requireValue(m.logicalPostKey === `rubyclips:${seriesId}:r16:p${part}`, 'the logical episode/part identity is invalid.');
  requireValue(m.segmentIndex === part && Number.isInteger(m.segmentTotal) && m.segmentTotal >= part, 'the part numbering is invalid.');
  requireValue(Array.isArray(m.sourceUrls) && m.sourceUrls.length === 1 && m.sourceUrls[0] === SPOTIFY_FEED, 'the sound must come from the selected Spotify show.');
  requireValue(finitePositive(m.segmentDurationSeconds) && m.segmentDurationSeconds <= 599, 'the clip duration is invalid.');
  requireValue(typeof m.file === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]*\.mp4$/.test(m.file) && !m.file.includes('..'), 'the MP4 filename is invalid.');
  requireValue(typeof m.caption === 'string' && m.caption.trim().length > 0 && m.caption.length <= 2200, 'the post caption is missing or too long.');
  // Older v16 receipts remain recoverable; a fresh upload needs all media proof.
  if (!forPublish) return { seriesId, index: part, total: m.segmentTotal };
  requireValue(/^[A-Za-z0-9]{22}$/.test(m.spotifyEpisodeId || ''), 'the precise Spotify episode is missing.');
  requireValue(m.sourceVideoVerified === true && m.sourceAudioVerified === true && m.fullEpisodeVerified === true, 'original full-episode video and audio must both be verified before rendering.');
  requireValue(m.visualMode === 'original-source-video', 'original video is required; artwork, waveforms, and previews are not accepted.');
  requireValue(['spotify-native', 'verified-creator-transport', 'verified-public-copy'].includes(m.sourceAccessMethod), 'the source access method is unverified.');
  if (m.sourceAccessMethod !== 'spotify-native') {
    const proof = m.sourceVerification || {};
    requireValue(proof.spotifyEpisodeId === m.spotifyEpisodeId && proof.fullCoverage === true, 'the alternate download must cover the same full Spotify episode.');
    requireValue(typeof proof.visualUrl === 'string' && /^https:\/\/(?:www\.)?facebook\.com\/(?:[^/?#]+\/videos\/(?:[^/?#]+\/)?[0-9]+|reel\/[0-9]+)\/?$/i.test(proof.visualUrl), 'the video transport must be a verified Facebook video.');
    requireValue(m.transportUrl === proof.visualUrl && m.transportAudioUsed === false, 'the video transport must agree with the measured proof and use Spotify sound.');
    requireValue(typeof proof.audioUrl === 'string' && /^https:\/\/anchor\.fm\/s\/10ff75318\/podcast\/play\//.test(proof.audioUrl), 'sound must come from this Spotify show\'s official episode feed.');
    requireValue(finitePositive(proof.audioCorrelation) && proof.audioCorrelation >= 0.90, 'source audio identity and timing have not been verified.');
    requireValue(proof.previewFrameVerified === true, 'the original Spotify visuals have not been matched.');
  }
  requireValue(finitePositive(m.sourceDurationSeconds), 'the verified full source duration is missing.');
  const media = m.sourceMedia || {};
  requireValue(media.fullEpisode === true && media.videoCodec && media.audioCodec, 'the measured original source must contain full video and audio.');
  for (const key of ['videoDurationSeconds', 'audioDurationSeconds']) {
    requireValue(finitePositive(media[key]) && media[key] >= m.sourceDurationSeconds - 0.2 && media[key] <= m.sourceDurationSeconds + 0.3, 'the declared duration must match the measured full original media.');
  }
  if (m.sourceAccessMethod !== 'spotify-native') {
    requireValue(finitePositive(m.sourceVerification.audioVerifiedDurationSeconds) && Math.abs(m.sourceVerification.audioVerifiedDurationSeconds - m.sourceDurationSeconds) <= 0.2, 'the complete matched Spotify soundtrack duration must be preserved.');
  }
  requireValue(typeof m.segmentStartSeconds === 'number' && Number.isFinite(m.segmentStartSeconds) && m.segmentStartSeconds >= 0 && finitePositive(m.segmentEndSeconds), 'the source time boundaries are missing.');
  requireValue(m.segmentEndSeconds > m.segmentStartSeconds && m.segmentEndSeconds <= m.sourceDurationSeconds + 0.2, 'the clip is outside the source episode.');
  requireValue(Math.abs(m.segmentDurationSeconds - (m.segmentEndSeconds - m.segmentStartSeconds)) <= 0.2, 'the encoded clip does not cover its requested source interval.');
  requireValue(part !== 1 || m.segmentStartSeconds === 0, 'the first part must begin at the start of the story.');
  requireValue(part !== m.segmentTotal || Math.abs(m.segmentEndSeconds - m.sourceDurationSeconds) <= 0.2, 'the last part must include the story ending.');
  requireValue(m.outputVideoCodec === 'h264' && m.outputAudioCodec === 'aac', 'the final MP4 must have verified H.264 video and AAC sound.');
  for (const stream of [m.mediaVideo, m.mediaAudio]) {
    requireValue(finitePositive(stream?.durationSeconds) && Math.abs(stream.durationSeconds - (m.segmentEndSeconds - m.segmentStartSeconds)) <= 0.2, 'each final audio and video stream must cover the complete requested part.');
  }
  return { seriesId, index: part, total: m.segmentTotal };
}

export function validatePendingSource(state, manifest, tag, now = Date.now()) {
  requireValue(state?.spotifyShowId === SPOTIFY_SHOW_ID && state?.targetChannel === RUBARATA_CHANNEL, 'the durable queue has a different source or account.');
  requireValue(!state.hold && !state.blocked && state.pending?.phase !== 'blocked', 'the queue requires attention before another upload.');
  requireValue(state.current?.guid === manifest.sourceEpisodeGuid && state.current?.next_part === manifest.segmentIndex, 'the episode or part is not the next item in the durable queue.');
  requireValue(state.pending?.releaseTag === tag && state.pending?.logicalPostKey === manifest.logicalPostKey, 'the pending upload must be saved before posting.');
  requireValue(!state.pending.spotifyEpisodeId || state.pending.spotifyEpisodeId === manifest.spotifyEpisodeId, 'the saved Spotify episode does not match the prepared video.');
  const last = state.last_post_at ? Date.parse(state.last_post_at) : null;
  requireValue(last === null || (Number.isFinite(last) && now - last >= 6 * 60 * 60 * 1000), 'six hours must pass after the last confirmed TikTok send.');
}

export function postMatchesMedia(post, manifest, videoUrl, organizationId) {
  if (!/^[a-f0-9]{24}$/.test(String(post?.id || '')) || post?.channel?.id !== RUBARATA_CHANNEL_ID || post?.text !== manifest.caption.trim()) return false;
  const backfill = `https://buffer-updates-media-backfill-bucket.s3.amazonaws.com/${organizationId}/${RUBARATA_CHANNEL_ID}/${post.id}_video.mp4`;
  return post?.assets?.some(asset => asset?.source === videoUrl || asset?.source === backfill) === true;
}
