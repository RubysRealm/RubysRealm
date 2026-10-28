import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

// Isolate only external dependencies; evaluate the complete production handler.
// No network, credentials, file writes, media generation or publishing is allowed.
const source = readFileSync(new URL('../api/rubyclips-post.js', import.meta.url), 'utf8')
  .replace(/import \{ createBufferVideoPost, getBufferTikTokChannel \} from '[^']+';/, 'const {createBufferVideoPost,getBufferTikTokChannel}=globalThis.__rubarataMocks;')
  .replace(/import \{[\s\S]*?\} from '\.\.\/lib\/rubarata-video\.js';/, 'const {RUBARATA_CHANNEL_ID,RUBARATA_CHANNEL,SPOTIFY_SHOW_ID,PUBLISHER_VERSION,parseReleaseTag,validateSpotifyVideoManifest,validatePendingSource,postMatchesMedia}=globalThis.__rubarataMocks;');
const channel = '6a9f6ff1cd8b9c702c2897e1';
const id = '6ae1f517f8ac381631f4104d';
const tag = 'rubyclips-tt-hisstory-db0dcc48f74238a8-r16-p1';
const videoUrl = `https://github.com/RubysRealm/RubysRealm/releases/download/${tag}/episode.mp4`;
const manifest = {file:'episode.mp4',caption:'Verified story caption',logicalPostKey:'exact-key'};
let creates = 0;
globalThis.__rubarataMocks = {
  RUBARATA_CHANNEL_ID:channel,RUBARATA_CHANNEL:'rubaradaclips',SPOTIFY_SHOW_ID:'6alyG1Jw4KH03mXZlYtPkf',PUBLISHER_VERSION:'hisstory-v17-durable-video',
  createBufferVideoPost:async()=>{creates++;throw Error('Publishing forbidden in tests');},
  getBufferTikTokChannel:async()=>({organization:{id:'org'},channel:{id:channel,name:'rubaradaclips'}}),
  parseReleaseTag:value=>{assert.equal(value,tag);},
  validateSpotifyVideoManifest:()=>({index:1,total:1}),
  validatePendingSource:()=>{throw Error('Lookup must never invoke publish guard');},
  postMatchesMedia:post=>post.channel.id===channel&&post.text===manifest.caption&&post.assets.some(a=>a.source===videoUrl)
};
const {default:handler,publishingErrorCodes} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
delete globalThis.__rubarataMocks;
const originalFetch = globalThis.fetch;
const originalKey = process.env.BUFFER_API_KEY;
process.env.BUFFER_API_KEY = 'test-only-not-a-credential';
async function lookup({diagnostics=true, denied=false, status='error', wrongChannel=false, missing=false}={}) {
  const requests=[];
  const post={id,text:manifest.caption,status,channel:{id:wrongChannel?'other':channel},assets:[{source:videoUrl}],sentAt:status==='sent'?'2026-10-28T02:03:07Z':null,externalLink:status==='sent'?'https://tiktok.com/@rubaradaclips/video/7701532975917321485':null,error:status==='error'?{message:'TikTok flagged this post as potential spam'}:null};
  globalThis.fetch=async(url,options={})=>{
    requests.push({url,options});
    if(url.endsWith('/manifest.json')) return Response.json(manifest);
    if(url.endsWith('/publish.json')) return Response.json({ok:true,channelName:'rubaradaclips',videoUrl,logicalPostKey:manifest.logicalPostKey,postId:id});
    assert.equal(url,'https://api.buffer.com');
    const body=JSON.parse(options.body);
    assert.match(body.query,/^query /);assert.doesNotMatch(body.query,/\bmutation\b/);
    assert.equal(body.variables.id,id);
    if(body.query.includes('RubarataPublishingError')) {
      if(denied) return Response.json({errors:[{message:'Internal field unavailable'}]});
      return Response.json({data:{post:{id,channel:{id:channel},error:{rawError:JSON.stringify({error:{code:'spam_risk',access_token:'never-expose-this-secret'},headers:{Authorization:'Bearer not-public'}}),supportUrl:'https://support.buffer.com/article?token=never-expose-this-secret'}}}});
    }
    return Response.json({data:{post:missing?null:post}});
  };
  const res={code:null,body:null,setHeader(){},status(code){this.code=code;return this;},json(body){this.body=body;return this;}};
  try{await handler({method:'GET',query:{lookupTag:tag,...(diagnostics?{diagnostics:'1'}:{})}},res);return {res,requests};}
  finally{globalThis.fetch=originalFetch;}
}
test('underlying provider codes are extracted without credentials',()=>{
  assert.deepEqual(publishingErrorCodes(JSON.stringify({error:{code:'spam_risk',access_token:'secret'}})),['spam_risk']);
  assert.deepEqual(publishingErrorCodes('TikTok: spam_risk_user_banned_from_posting'),['spam_risk_user_banned_from_posting']);
  assert.deepEqual(publishingErrorCodes(JSON.stringify({data:{fail_reason:'video_pull_failed'},headers:{code:'secret'},access_token:'secret'})),['video_pull_failed']);
  assert.deepEqual(publishingErrorCodes(null),[]);
});
test('exact rejected-post lookup adds codes without sending or changing status',async()=>{
 const {res,requests}=await lookup();assert.equal(res.code,200);assert.equal(res.body.post.status,'error');assert.equal(res.body.post.sentAt,null);assert.equal(res.body.post.externalLink,null);assert.deepEqual(res.body.publishingDiagnostics.serviceCodes,['spam_risk']);assert.equal(res.body.publishingDiagnostics.supportUrl,'https://support.buffer.com/article');assert(!JSON.stringify(res.body).includes('never-expose-this-secret'));assert.equal(requests.length,4);assert.equal(creates,0);
});
test('unavailable internal diagnostic field does not break exact reconciliation',async()=>{
 const {res}=await lookup({denied:true});assert.equal(res.code,200);assert.equal(res.body.post.status,'error');assert.equal(res.body.publishingDiagnostics.available,false);assert.equal(creates,0);
});
test('normal queue lookups have no extra diagnostic request',async()=>{
 const {res,requests}=await lookup({diagnostics:false});assert.equal(res.code,200);assert.equal(requests.length,3);assert(!('publishingDiagnostics' in res.body));assert.equal(creates,0);
});
test('sent posts remain sent and do not request rejection diagnostics',async()=>{
 const {res,requests}=await lookup({status:'sent'});assert.equal(res.code,200);assert.equal(res.body.post.status,'sent');assert.equal(requests.length,3);assert.equal(creates,0);
});
test('wrong channel stops lookup without a diagnostic query or creation',async()=>{
 const {res,requests}=await lookup({wrongChannel:true});assert.equal(res.code,503);assert.equal(requests.length,3);assert.equal(creates,0);
});
test('missing known post is not recreated',async()=>{
 const {res,requests}=await lookup({missing:true});assert.equal(res.code,503);assert.equal(requests.length,3);assert.equal(creates,0);
});
test.after(()=>{if(originalKey===undefined)delete process.env.BUFFER_API_KEY;else process.env.BUFFER_API_KEY=originalKey;globalThis.fetch=originalFetch;});
