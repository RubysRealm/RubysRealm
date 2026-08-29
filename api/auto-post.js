import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT='https://api.buffer.com';
const RELEASE_OWNER='RubysRealm';
const RELEASE_REPO='RubysRealm';
const REQUIRED_RENDERER='reference-narration-story-v2';
const REQUIRED_GATE='reference-photographic-story-v2';
const MIN_SECONDS=120;
const MAX_SECONDS=540;

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
  const d=await gql(`query Posts($organizationId: OrganizationId!, $channelId: ChannelId!) { posts(first: 40,input:{organizationId:$organizationId,filter:{status:[scheduled,sent],channelIds:[$channelId]},sort:[{field:createdAt,direction:desc}]}) { edges { node { id status dueAt sentAt externalLink assets { source } } } } }`,{organizationId:target.organization.id,channelId:target.channel.id});
  return (d?.posts?.edges||[]).map(e=>e.node);
}

function validateManifest(m){
  if(!m?.qualityPassed) throw new Error('Blocked: v2 quality gate did not pass.');
  if(m.renderer!==REQUIRED_RENDERER) throw new Error('Blocked: wrong renderer.');
  if(m.qualityGate!==REQUIRED_GATE) throw new Error('Blocked: wrong quality gate.');
  if(!m.checks || !Object.values(m.checks).every(Boolean)) throw new Error('Blocked: one or more v2 checks failed.');
  const duration=Number(m.durationSeconds);
  if(!Number.isFinite(duration) || duration<MIN_SECONDS || duration>MAX_SECONDS) throw new Error('Blocked: duration outside 2-9 minutes.');
  if(Number(m.photoSourceRatio||0)<0.65) throw new Error('Blocked: insufficient legitimate photographic sourcing.');
  if(Number(m.visualInsertCount||0)<8) throw new Error('Blocked: insufficient contextual visual support.');
  if(Number(m.captionMaxWords||99)>4) throw new Error('Blocked: caption chunks are too large.');
  if(!m.file || !String(m.file).endsWith('.mp4')) throw new Error('Blocked: invalid final media file.');
}

export default async function handler(req,res){
  if(req.method!=='GET') return res.status(405).json({ok:false,error:'Method not allowed'});
  try{
    const tag=String(req.query?.tag||'').trim();
    if(!/^reference-story-[0-9]+$/.test(tag)) throw new Error('A valid reference-story release tag is required.');
    const base=`https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
    const manifestUrl=`${base}/manifest.json`;
    const mr=await fetch(manifestUrl,{redirect:'follow',cache:'no-store'});
    if(!mr.ok) throw new Error(`Approved manifest unavailable (${mr.status}).`);
    const manifest=await mr.json();
    validateManifest(manifest);
    const videoUrl=`${base}/${encodeURIComponent(manifest.file)}`;
    const head=await fetch(videoUrl,{method:'HEAD',redirect:'follow',cache:'no-store'});
    if(!head.ok) throw new Error(`Approved v2 MP4 unavailable (${head.status}).`);

    const target=await getBufferTikTokChannel();
    if(!target) throw new Error('No TikTok channel is connected in Buffer.');
    const existing=await recentPosts(target);
    const duplicate=existing.find(p=>p?.assets?.some(a=>a?.source===videoUrl));
    if(duplicate) return res.status(200).json({ok:true,skipped:true,postId:duplicate.id,status:duplicate.status,externalLink:duplicate.externalLink||null,renderer:REQUIRED_RENDERER});

    const caption=`${String(manifest.title||"Ruby's Realm Story")} ${String(manifest.part||'Part 1')} #storytime #storytok #aistory #rubysrealm`;
    const dueAt=new Date(Date.now()+90*1000).toISOString();
    const post=await createBufferVideoPost({channelId:target.channel.id,caption,videoUrl,dueAt});
    return res.status(200).json({ok:true,postId:post.id,status:post.status,dueAt,videoUrl,renderer:REQUIRED_RENDERER,qualityPassed:true,durationSeconds:Number(manifest.durationSeconds),photoSourceRatio:Number(manifest.photoSourceRatio),visualInsertCount:Number(manifest.visualInsertCount)});
  }catch(e){
    console.error('reference v2 publish failed',e);
    return res.status(500).json({ok:false,error:e.message});
  }
}
