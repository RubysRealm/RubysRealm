import sharp from 'sharp';
import { createRemoteJWKSet, jwtVerify } from 'jose';

const GITHUB_JWKS=createRemoteJWKSet(new URL('https://token.actions.githubusercontent.com/.well-known/jwks'));
const AUDIENCE='rubys-realm-image-generator';
const REPOSITORY='RubysRealm/RubysRealm';
const WORKFLOW='.github/workflows/tiktok-animated-story.yml';
const GATEWAY='https://ai-gateway.vercel.sh/v1';

async function verifyCaller(auth){
  const token=String(auth||'').replace(/^Bearer\s+/i,'').trim();
  if(!token) throw new Error('Missing GitHub Actions OIDC token.');
  const {payload}=await jwtVerify(token,GITHUB_JWKS,{issuer:'https://token.actions.githubusercontent.com',audience:AUDIENCE});
  if(payload.repository!==REPOSITORY) throw new Error('OIDC repository is not authorized.');
  if(payload.ref!=='refs/heads/main') throw new Error('OIDC ref is not authorized.');
  const workflowRef=String(payload.workflow_ref||'');
  if(!workflowRef.includes(`${REPOSITORY}/${WORKFLOW}@refs/heads/main`)) throw new Error('OIDC workflow is not authorized.');
  if(!['push','schedule','workflow_dispatch'].includes(String(payload.event_name||''))) throw new Error('OIDC event is not authorized.');
  return payload;
}

async function gatewayCredits(token){
  const r=await fetch(`${GATEWAY}/credits`,{headers:{Authorization:`Bearer ${token}`},cache:'no-store'});
  if(!r.ok) throw new Error(`AI Gateway credits check failed (${r.status}).`);
  const d=await r.json();
  const balance=Number(d.balance||0);
  if(!Number.isFinite(balance)) throw new Error('AI Gateway returned an invalid credit balance.');
  return balance;
}

export default async function handler(req,res){
  if(req.method!=='POST') return res.status(405).json({ok:false,error:'Method not allowed'});
  try{
    await verifyCaller(req.headers.authorization);
    const body=typeof req.body==='string'?JSON.parse(req.body||'{}'):(req.body||{});
    const beat=String(body.beat||'').replace(/\s+/g,' ').trim();
    const title=String(body.title||"Ruby's Realm Story").replace(/\s+/g,' ').trim();
    const index=Number(body.index||0);
    if(!beat || beat.length>1400) throw new Error('A valid story beat is required.');
    if(!Number.isInteger(index) || index<0 || index>24) throw new Error('Invalid scene index.');

    const gatewayToken=process.env.AI_GATEWAY_API_KEY||process.env.VERCEL_OIDC_TOKEN;
    if(!gatewayToken) throw new Error('Vercel AI Gateway authorization is unavailable.');
    const reserve=Number(process.env.AI_IMAGE_CREDIT_RESERVE||0.75);
    const balance=await gatewayCredits(gatewayToken);
    if(balance<=reserve) return res.status(402).json({ok:false,error:'Existing AI Gateway credit reserve reached; no paid top-up will be attempted.',balance,reserve});

    const model=process.env.AI_IMAGE_MODEL||'openai/gpt-image-2';
    const prompt=[
      'Create a polished stylized 3D animated story illustration for a vertical social storytelling video.',
      'Visual target: cinematic simplified cartoon people and environments, expressive but clean character design, soft realistic lighting, dimensional depth, polished AI-rendered look similar to a modern animated explainer.',
      'No text, no captions, no labels, no logos, no watermark.',
      'Use a consistent recurring protagonist when a person belongs in the scene: adult man with shaved head, charcoal hoodie, dark pants, simple expressive face.',
      'The image must clearly and literally depict the current story beat, including the most important location, object, action, clue, emotion, or discovery.',
      'Compose the important subject center-left or center and keep the lower-center region readable for an overlaid one-word caption.',
      `Story title: ${title}.`,
      `Current beat: ${beat}`
    ].join(' ');

    const r=await fetch(`${GATEWAY}/images/generations`,{
      method:'POST',
      headers:{Authorization:`Bearer ${gatewayToken}`,'Content-Type':'application/json'},
      body:JSON.stringify({model,prompt,n:1,response_format:'b64_json'}),
    });
    const data=await r.json().catch(()=>({}));
    if(!r.ok) throw new Error(`AI image generation failed (${r.status}): ${String(data?.error?.message||data?.message||'unknown error').slice(0,240)}`);
    const item=(data.data||[])[0]||{};
    let input;
    if(item.b64_json) input=Buffer.from(item.b64_json,'base64');
    else if(item.url){
      const ir=await fetch(item.url);
      if(!ir.ok) throw new Error(`Generated image download failed (${ir.status}).`);
      input=Buffer.from(await ir.arrayBuffer());
    }else throw new Error('AI Gateway returned no image data.');

    const output=await sharp(input).rotate().resize(1024,1280,{fit:'cover',position:'centre'}).jpeg({quality:90,mozjpeg:true}).toBuffer();
    res.setHeader('Content-Type','image/jpeg');
    res.setHeader('Cache-Control','no-store');
    res.setHeader('X-Rubys-Realm-Image-Model',model);
    res.setHeader('X-Rubys-Realm-Credit-Balance-Before',String(balance));
    return res.status(200).send(output);
  }catch(e){
    console.error('story-image generation failed',e);
    return res.status(500).json({ok:false,error:e.message});
  }
}
