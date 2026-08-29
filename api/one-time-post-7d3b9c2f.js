import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const VIDEO_URL = 'https://files2.heygen.ai/aws_pacific/avatar_tmp/1592f1dded57439e808601ba8fbe8818/v56b41eb600f34f519d05f4e72cbfd9b8/2c5e7970d84543b78a25377676d5bd88.mp4?Expires=1788555357&Signature=Tmv433zLkOjMF9gh1DYcGnT9Bk0LONVh7yK8NT7VM0-H9B7AvdorgY1cLbIdKqGa~Cp3-W92AOp3noeZqoG3I7WcNWFgPaDIEQOiw28aIbhE5MDwYyxrAMoTiyyQ5wWYuv6LcMQplNkhBVYltyj8Yi3u~mQyqdHWT3y66nw8k1n~lDBLJpKtaVXJQ2xp19drcPTSq8Bb7s51sSTtbXlnM8RWGOJw1RezBOuEP4umCHtnWQnlHA4K3YQg2C~7kh1lxIdPCeWEeVQ3YywUywRvUARClGvftlnP94QOOo9jZayqfSzCseKzW0xh7XDXpryTbGw1DmEPXJ8IT6JlyL0QPw__&Key-Pair-Id=K38HBHX5LX3X2H';

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ ok:false });
  try {
    const target = await getBufferTikTokChannel();
    if (!target) throw new Error('No TikTok channel connected.');
    const dueAt = new Date(Date.now() + 2 * 60 * 1000).toISOString();
    const post = await createBufferVideoPost({
      channelId: target.channel.id,
      caption: 'Something moved in the hallway. #StoryTok #AIGenerated #Suspense',
      videoUrl: VIDEO_URL,
      dueAt
    });
    return res.status(200).json({ ok:true, postId:post.id, status:post.status, dueAt });
  } catch (error) {
    return res.status(500).json({ ok:false, error:error.message });
  }
}
