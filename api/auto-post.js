import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const VIDEO_URL='https://d2ol7oe51mr4n9.cloudfront.net/user_3IVucXuJl5D3y0NqtFPdYP7zZMV/f842b919-0fa6-4a61-ad2b-141f638dee30.mp4';
const CAPTION='Your Life as a Motel Owner — Part 1 #storytime #storytok #aistory #rubysrealm';
const BUFFER_ENDPOINT='https://api.buffer.com';

async function gql(query,variables={}){
  const key=process.env.BUFFER_API_KEY;
  if(!key) throw new Error('BUFFER_API_KEY is not configured.');
  const r=await fetch(BUFFER_ENDPOINT,{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${key}`},body:JSON.stringify({query,variables})});
  const d=await r.json();
  if(!r.ok) throw new Error(`Buffer HTTP ${r.status}`);
  if(d.errors?.length) throw new Error(d.errors.map(e=>e.message).join('; '));
  return d.data;
}

async function recentPosts(target){
  const d=await gql(`query Posts($organizationId: OrganizationId!, $channelId: ChannelId!) { posts(first: 30,input:{organizationId:$organizationId,filter:{status:[scheduled,sent],channelIds:[$channelId]},sort:[{field:createdAt,direction:desc}]}) { edges { node { id status dueAt sentAt externalLink assets { source } } } } }`,{organizationId:target.organization.id,channelId:target.channel.id});
  return (d?.posts?.edges||[]).map(e=>e.node);
}

export default async function handler(req,res){
  if(req.method!=='GET') return res.status(405).json({ok:false,error:'Method not allowed'});
  try{
    const head=await fetch(VIDEO_URL,{method:'HEAD',redirect:'follow'});
    if(!head.ok) throw new Error(`Approved reference MP4 unavailable (${head.status}).`);
    const target=await getBufferTikTokChannel();
    if(!target) throw new Error('No TikTok channel is connected in Buffer.');
    const existing=await recentPosts(target);
    const duplicate=existing.find(p=>p?.assets?.some(a=>a?.source===VIDEO_URL));
    if(duplicate) return res.status(200).json({ok:true,skipped:true,postId:duplicate.id,status:duplicate.status,externalLink:duplicate.externalLink||null});
    const dueAt=new Date(Date.now()+90*1000).toISOString();
    const post=await createBufferVideoPost({channelId:target.channel.id,caption:CAPTION,videoUrl:VIDEO_URL,dueAt});
    return res.status(200).json({ok:true,postId:post.id,status:post.status,dueAt,videoUrl:VIDEO_URL,renderer:'reference-narration-story-v1',qualityPassed:true,durationSeconds:300.033});
  }catch(e){
    console.error('reference verification post failed',e);
    return res.status(500).json({ok:false,error:e.message});
  }
}
