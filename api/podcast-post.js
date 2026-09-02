import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT='https://api.buffer.com';
const RELEASE_OWNER='RubysRealm';
const RELEASE_REPO='RubysRealm';

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
  const d=await gql(`query Posts($organizationId: OrganizationId!, $channelId: ChannelId!) { posts(first: 60,input:{organizationId:$organizationId,filter:{status:[scheduled,sent],channelIds:[$channelId]},sort:[{field:createdAt,direction:desc}]}) { edges { node { id status dueAt sentAt externalLink text assets { source } } } } }`,{organizationId:target.organization.id,channelId:target.channel.id});
  return (d?.posts?.edges||[]).map(e=>e.node);
}

function validateManifest(m){
  if(m?.platform!=='rubys-realm-podcast-repost-v1') throw new Error('Blocked: invalid podcast repost manifest.');
  if(!m?.storyId || !m?.title) throw new Error('Blocked: missing story identity.');
  const part=Number(m.partNumber), total=Number(m.totalParts);
  if(!Number.isInteger(part)||!Number.isInteger(total)||part<1||total<1||part>total) throw new Error('Blocked: invalid part numbering.');
  const duration=Number(m.durationSeconds);
  if(!Number.isFinite(duration)||duration<30||duration>600) throw new Error('Blocked: part duration outside 30 seconds to 10 minutes.');
  if(!m.file || !String(m.file).endsWith('.mp4')) throw new Error('Blocked: invalid video file.');
  if(!m.partLabel) throw new Error('Blocked: missing part label.');
}

export default async function handler(req,res){
  if(req.method!=='GET') return res.status(405).json({ok:false,error:'Method not allowed'});
  try{
    const tag=String(req.query?.tag||'').trim();
    if(!/^podcast-part-[0-9]+$/.test(tag)) return res.status(400).json({ok:false,error:'A valid podcast-part release tag is required.'});
    const base=`https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
    const mr=await fetch(`${base}/manifest.json`,{redirect:'follow',cache:'no-store'});
    if(!mr.ok) throw new Error(`Podcast manifest unavailable (${mr.status}).`);
    const manifest=await mr.json();
    validateManifest(manifest);
    const videoUrl=`${base}/${encodeURIComponent(manifest.file)}`;
    const head=await fetch(videoUrl,{method:'HEAD',redirect:'follow',cache:'no-store'});
    if(!head.ok) throw new Error(`Podcast MP4 unavailable (${head.status}).`);

    const target=await getBufferTikTokChannel();
    if(!target) throw new Error('No TikTok channel is connected in Buffer.');
    const existing=await recentPosts(target);
    const duplicate=existing.find(p=>p?.assets?.some(a=>a?.source===videoUrl));
    if(duplicate) return res.status(200).json({ok:true,skipped:true,postId:duplicate.id,status:duplicate.status,externalLink:duplicate.externalLink||null});

    const caption=`${manifest.title} — Part ${manifest.partNumber}/${manifest.totalParts}: ${manifest.partLabel} #storytime #storytok #pov #rubysrealm`;
    const dueAt=new Date(Date.now()+60*1000).toISOString();
    const post=await createBufferVideoPost({channelId:target.channel.id,caption,videoUrl,dueAt});
    return res.status(200).json({ok:true,postId:post.id,status:post.status,dueAt,caption,storyId:manifest.storyId,partNumber:Number(manifest.partNumber),totalParts:Number(manifest.totalParts),videoUrl});
  }catch(e){
    console.error('podcast post failed',e);
    return res.status(500).json({ok:false,error:e.message});
  }
}
