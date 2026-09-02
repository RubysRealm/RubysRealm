import { getBufferTikTokChannel, createBufferVideoPost } from '../lib/buffer.js';

const BUFFER_ENDPOINT='https://api.buffer.com';
const RELEASE_OWNER='RubysRealm';
const RELEASE_REPO='RubysRealm';
const REQUIRED_RENDERER='reference-illustrated-story-v7';
const REQUIRED_GATE='reference-example-target-v7';
const MIN_SECONDS=120;
const MAX_SECONDS=540;
const MIN_GENERATED_ILLUSTRATION_RATIO=1.0;

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
  const d=await gql(`query Posts($organizationId: OrganizationId!, $channelId: ChannelId!) { posts(first: 60,input:{organizationId:$organizationId,filter:{status:[scheduled,sent],channelIds:[$channelId]},sort:[{field:createdAt,direction:desc}]}) { edges { node { id text status dueAt sentAt externalLink assets { source } } } } }`,{organizationId:target.organization.id,channelId:target.channel.id});
  return (d?.posts?.edges||[]).map(e=>e.node);
}

function validateManifest(m){
  if(!m?.qualityPassed) throw new Error('Blocked: exact-target quality gate did not pass.');
  if(m.renderer!==REQUIRED_RENDERER) throw new Error('Blocked: wrong renderer.');
  if(m.qualityGate!==REQUIRED_GATE) throw new Error('Blocked: wrong quality gate.');
  if(!m.checks || !Object.values(m.checks).every(Boolean)) throw new Error('Blocked: one or more exact-target checks failed.');
  const duration=Number(m.durationSeconds);
  if(!Number.isFinite(duration) || duration<MIN_SECONDS || duration>MAX_SECONDS) throw new Error('Blocked: duration outside 2-9 minutes.');
  if(Number(m.visualCoverageRatio||0)<0.98) throw new Error('Blocked: storytelling area is not continuously image-filled.');
  if(Number(m.visualInsertCount||0)<10) throw new Error('Blocked: insufficient story-matched scenes.');
  if(Number(m.captionMaxWords||99)!==1) throw new Error('Blocked: captions are not exact one-word narration cues.');
  if(m?.style?.lower_panel!=='none') throw new Error('Blocked: teal lower panel is still enabled.');
  if(m?.style?.caption_timing!=='direct-neural-word-boundaries') throw new Error('Blocked: captions are not tied directly to narration word boundaries.');
  if(Number(m?.style?.generated_illustration_ratio||0)<MIN_GENERATED_ILLUSTRATION_RATIO) throw new Error('Blocked: every production visual must be a generated cartoon illustration.');
  if(!/^sha256:[a-f0-9]{64}$/i.test(String(m.storyFingerprint||''))) throw new Error('Blocked: story duplicate fingerprint is missing.');
  if(!/^sha256:[a-f0-9]{64}$/i.test(String(m.videoFingerprint||''))) throw new Error('Blocked: video duplicate fingerprint is missing.');
  if(m.duplicateGuard!=='story-and-video-sha256-v1') throw new Error('Blocked: duplicate guard is not enabled.');
  if(!m.file || !String(m.file).endsWith('.mp4')) throw new Error('Blocked: invalid final media file.');
}

function validatePodcastManifest(m){
  if(m?.platform!=='rubys-realm-podcast-repost-v1') throw new Error('Blocked: invalid podcast repost manifest.');
  if(!m?.storyId || !m?.title) throw new Error('Blocked: missing story identity.');
  const part=Number(m.partNumber), total=Number(m.totalParts), duration=Number(m.durationSeconds);
  if(!Number.isInteger(part)||!Number.isInteger(total)||part<1||total<1||part>total) throw new Error('Blocked: invalid part numbering.');
  if(!Number.isFinite(duration)||duration<30||duration>600) throw new Error('Blocked: podcast part duration outside 30 seconds to 10 minutes.');
  if(!m.file || !String(m.file).endsWith('.mp4')) throw new Error('Blocked: invalid podcast video file.');
  if(!m.partLabel) throw new Error('Blocked: missing podcast part label.');
  if(m.storyTitleBurnedIn!==true) throw new Error('Blocked: podcast story title is not burned into the video.');
  if(m.partLabelBurnedIn!==true) throw new Error('Blocked: podcast part number is not burned into the video.');
  if(m.captionsBurnedIn!==true) throw new Error('Blocked: podcast narration captions are not burned into the video.');
  if(m.captionTiming!=='word-timestamped narration transcription') throw new Error('Blocked: podcast captions are not narration-synced.');
}

function releaseTagFromSource(source){
  const m=String(source||'').match(/github\.com\/RubysRealm\/RubysRealm\/releases\/download\/([^/]+)\//i);
  if(!m) return null;
  try{return decodeURIComponent(m[1]);}catch{return m[1];}
}

async function priorPublishedManifests(posts,currentTag){
  const byTag=new Map();
  for(const post of posts){
    for(const asset of post?.assets||[]){
      const tag=releaseTagFromSource(asset?.source);
      if(tag && tag!==currentTag && !byTag.has(tag)) byTag.set(tag,post);
    }
  }
  const tags=[...byTag.keys()].filter(t=>/^reference-story-/.test(t)).slice(0,24);
  const results=await Promise.allSettled(tags.map(async tag=>{
    const url=`https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}/manifest.json`;
    const r=await fetch(url,{redirect:'follow',cache:'no-store'});
    if(!r.ok) throw new Error(`prior manifest ${tag} unavailable (${r.status})`);
    return {tag,post:byTag.get(tag),manifest:await r.json()};
  }));
  const ok=results.filter(r=>r.status==='fulfilled').map(r=>r.value);
  if(tags.length && !ok.length) throw new Error('Duplicate check could not verify prior published release manifests; refusing to risk a repeat upload.');
  return ok;
}

function sameProduction(current,prior){
  if(current.videoFingerprint && prior.videoFingerprint && current.videoFingerprint===prior.videoFingerprint) return 'video-fingerprint';
  if(current.storyFingerprint && prior.storyFingerprint && current.storyFingerprint===prior.storyFingerprint) return 'story-fingerprint';
  if(current.file && prior.file && current.file===prior.file) return 'legacy-file-name';
  return null;
}

async function postPodcast(tag,res){
  const base=`https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
  const mr=await fetch(`${base}/manifest.json`,{redirect:'follow',cache:'no-store'});
  if(!mr.ok) throw new Error(`Podcast manifest unavailable (${mr.status}).`);
  const manifest=await mr.json();
  validatePodcastManifest(manifest);
  const videoUrl=`${base}/${encodeURIComponent(manifest.file)}`;
  const head=await fetch(videoUrl,{method:'HEAD',redirect:'follow',cache:'no-store'});
  if(!head.ok) throw new Error(`Podcast MP4 unavailable (${head.status}).`);
  const target=await getBufferTikTokChannel();
  if(!target) throw new Error('No TikTok channel is connected in Buffer.');
  const existing=await recentPosts(target);
  const caption=`${manifest.title} — Part ${manifest.partNumber}/${manifest.totalParts}: ${manifest.partLabel} #storytime #storytok #pov #rubysrealm`;
  const duplicate=existing.find(p=>p?.assets?.some(a=>a?.source===videoUrl));
  const checkOnly=String(res.req?.query?.check||'')==='1';
  if(checkOnly) return res.status(200).json({ok:true,exists:Boolean(duplicate),postId:duplicate?.id||null,status:duplicate?.status||null,externalLink:duplicate?.externalLink||null,caption,storyId:manifest.storyId,partNumber:Number(manifest.partNumber),videoUrl});
  if(duplicate) return res.status(200).json({ok:true,skipped:true,postId:duplicate.id,status:duplicate.status,externalLink:duplicate.externalLink||null,caption,storyId:manifest.storyId,partNumber:Number(manifest.partNumber)});
  const dueAt=new Date(Date.now()+60*1000).toISOString();
  const post=await createBufferVideoPost({channelId:target.channel.id,caption,videoUrl,dueAt});
  return res.status(200).json({ok:true,postId:post.id,status:post.status,dueAt,caption,storyId:manifest.storyId,partNumber:Number(manifest.partNumber),totalParts:Number(manifest.totalParts),videoUrl,renderer:'podcast-repost-v2'});
}

export default async function handler(req,res){
  if(req.method!=='GET') return res.status(405).json({ok:false,error:'Method not allowed'});
  try{
    const tag=String(req.query?.tag||'').trim();
    if(/^podcast-part-[A-Za-z0-9_-]+$/.test(tag)) return await postPodcast(tag,res);
    if(!/^reference-story-[0-9]+$/.test(tag)) return res.status(400).json({ok:false,error:'A valid reference-story or podcast-part release tag is required.'});
    const base=`https://github.com/${RELEASE_OWNER}/${RELEASE_REPO}/releases/download/${encodeURIComponent(tag)}`;
    const manifestUrl=`${base}/manifest.json`;
    const mr=await fetch(manifestUrl,{redirect:'follow',cache:'no-store'});
    if(!mr.ok) throw new Error(`Approved manifest unavailable (${mr.status}).`);
    const manifest=await mr.json();
    validateManifest(manifest);
    const videoUrl=`${base}/${encodeURIComponent(manifest.file)}`;
    const head=await fetch(videoUrl,{method:'HEAD',redirect:'follow',cache:'no-store'});
    if(!head.ok) throw new Error(`Approved target MP4 unavailable (${head.status}).`);

    const target=await getBufferTikTokChannel();
    if(!target) throw new Error('No TikTok channel is connected in Buffer.');
    const existing=await recentPosts(target);
    const exactUrlDuplicate=existing.find(p=>p?.assets?.some(a=>a?.source===videoUrl));
    if(exactUrlDuplicate) return res.status(200).json({ok:true,skipped:true,duplicateReason:'exact-release-url',postId:exactUrlDuplicate.id,status:exactUrlDuplicate.status,externalLink:exactUrlDuplicate.externalLink||null,renderer:REQUIRED_RENDERER});

    const prior=await priorPublishedManifests(existing,tag);
    for(const item of prior){
      const reason=sameProduction(manifest,item.manifest||{});
      if(reason) return res.status(200).json({ok:true,skipped:true,duplicateReason:reason,duplicateRelease:item.tag,postId:item.post?.id||null,status:item.post?.status||'sent',externalLink:item.post?.externalLink||null,renderer:REQUIRED_RENDERER});
    }

    const caption=`${String(manifest.title||"Ruby's Realm Story")} ${String(manifest.part||'Part 1')} #storytime #storytok #aistory #rubysrealm`;
    const dueAt=new Date(Date.now()+90*1000).toISOString();
    const post=await createBufferVideoPost({channelId:target.channel.id,caption,videoUrl,dueAt});
    return res.status(200).json({ok:true,postId:post.id,status:post.status,dueAt,videoUrl,renderer:REQUIRED_RENDERER,qualityPassed:true,durationSeconds:Number(manifest.durationSeconds),visualCoverageRatio:Number(manifest.visualCoverageRatio),visualInsertCount:Number(manifest.visualInsertCount),voice:manifest?.style?.voice_used||null,generatedIllustrationRatio:Number(manifest?.style?.generated_illustration_ratio||0),storyFingerprint:manifest.storyFingerprint,videoFingerprint:manifest.videoFingerprint});
  }catch(e){
    console.error('auto-post failed',e);
    return res.status(500).json({ok:false,error:e.message});
  }
}
