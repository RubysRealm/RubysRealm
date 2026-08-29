import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT='https://api.buffer.com';
const OWNER='RubysRealm';
const REPO='RubysRealm';
const RENDERER='reference-narration-story-v1';
const GATE='reference-narration-clean-screen-v1';

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

function validTag(tag){ return /^reference-story-\d+$/.test(tag); }
function validate(m){
  if(!m||m.renderer!==RENDERER) throw new Error('Wrong renderer.');
  if(m.qualityGate!==GATE||m.qualityPassed!==true) throw new Error('Reference-style quality gate did not pass.');
  const checks=m.checks||{};
  if(!Object.keys(checks).length||Object.values(checks).some(v=>v!==true)) throw new Error('One or more required quality checks failed.');
  const d=Number(m.durationSeconds);
  if(!Number.isFinite(d)||d<120||d>540) throw new Error('Video duration is outside the 2-9 minute range.');
  if(!m.file||!String(m.file).endsWith('.mp4')) throw new Error('Manifest video file is invalid.');
}

export default async function handler(req,res){
  if(req.method!=='GET') return res.status(405).json({ok:false,error:'Method not allowed'});
  try{
    const tag=String(req.query?.tag||'');
    if(!validTag(tag)) return res.status(400).json({ok:false,error:'A valid reference-story release tag is required.'});
    const manifestUrl=`https://github.com/${OWNER}/${REPO}/releases/download/${tag}/manifest.json`;
    const mr=await fetch(manifestUrl,{redirect:'follow',cache:'no-store'});
    if(!mr.ok) throw new Error(`Approved manifest unavailable (${mr.status}).`);
    const manifest=await mr.json(); validate(manifest);
    const videoUrl=`https://github.com/${OWNER}/${REPO}/releases/download/${tag}/${encodeURIComponent(manifest.file)}`;
    const head=await fetch(videoUrl,{method:'HEAD',redirect:'follow'});
    if(!head.ok) throw new Error(`Approved MP4 unavailable (${head.status}).`);
    const target=await getBufferTikTokChannel();
    if(!target) throw new Error('No TikTok channel is connected in Buffer.');
    const existing=await recentPosts(target);
    const duplicate=existing.find(p=>p?.assets?.some(a=>a?.source===videoUrl));
    if(duplicate) return res.status(200).json({ok:true,skipped:true,postId:duplicate.id,status:duplicate.status,externalLink:duplicate.externalLink||null});
    const dueAt=new Date(Date.now()+60*1000).toISOString();
    const caption=String(manifest.caption||`${manifest.title||"Ruby's Realm Story"} ${manifest.part||'Part 1'} #storytime #storytok #aistory #rubysrealm`);
    const post=await createBufferVideoPost({channelId:target.channel.id,caption,videoUrl,dueAt});
    return res.status(200).json({ok:true,postId:post.id,status:post.status,dueAt,videoUrl,renderer:RENDERER,qualityPassed:true});
  }catch(e){
    console.error('reference auto-post failed',e);
    return res.status(500).json({ok:false,error:e.message});
  }
}
