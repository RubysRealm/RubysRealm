const fs=require('fs');
const {execFileSync}=require('child_process');
const Tiktok=require('@tobyg74/tiktok-api-dl');

const episodes=[
  {n:1,url:'https://www.tiktok.com/@muffindrama_us/video/7682997000391904526'},
  {n:2,url:'https://www.tiktok.com/shortdrama/episode/7682993954661553173/2'},
  {n:3,url:'https://www.tiktok.com/shortdrama/episode/7682993954661553173/3'},
  {n:4,url:'https://www.tiktok.com/shortdrama/episode/7682993954661553173/4'}
];

function collectUrls(value,path='',out=[]){
  if(typeof value==='string' && /^https?:\/\//i.test(value)) out.push({url:value,path});
  else if(Array.isArray(value)) value.forEach((v,i)=>collectUrls(v,`${path}[${i}]`,out));
  else if(value && typeof value==='object') Object.entries(value).forEach(([k,v])=>collectUrls(v,path?`${path}.${k}`:k,out));
  return out;
}
function pickMedia(r){
  const urls=collectUrls(r);
  const scored=urls.map(x=>{
    const p=x.path.toLowerCase(), u=x.url.toLowerCase();
    let s=0;
    if(/video|playaddr|downloadaddr|download|play/.test(p)) s+=40;
    if(/\.mp4(?:\?|$)|video\/tos|tikcdn|tiktokcdn|byteoversea|ssstik|muscdn|snaptik/.test(u)) s+=30;
    if(/cover|avatar|image|music|audio|thumb/.test(p)) s-=80;
    return {...x,score:s};
  }).sort((a,b)=>b.score-a.score);
  return scored.length && scored[0].score>0 ? scored[0].url : null;
}
function pickId(r){
  const vals=[r?.result?.id,r?.result?.video?.id,r?.result?.aweme_id,r?.result?.awemeId,r?.id];
  for(const v of vals){ const s=String(v||'').trim(); if(/^\d{10,25}$/.test(s)) return s; }
  return null;
}
async function resolve(url,epn){
  let bestId=null;
  for(const version of ['v2','v1','v3']){
    try{
      const r=await Tiktok.Downloader(url,{version});
      fs.writeFileSync(`rubyclips/muffin_work/resolver-ep${epn}-${version}.json`,JSON.stringify(r,null,2));
      bestId=pickId(r)||bestId;
      const media=pickMedia(r);
      if(media) return {media,id:bestId,version};
    }catch(e){
      fs.writeFileSync(`rubyclips/muffin_work/resolver-ep${epn}-${version}-error.txt`,String(e?.stack||e));
    }
  }
  if(bestId){
    const canonical=`https://www.tiktok.com/@muffindrama_us/video/${bestId}`;
    for(const version of ['v2','v1','v3']){
      try{
        const r=await Tiktok.Downloader(canonical,{version});
        fs.writeFileSync(`rubyclips/muffin_work/resolver-ep${epn}-canonical-${version}.json`,JSON.stringify(r,null,2));
        const media=pickMedia(r);
        if(media) return {media,id:pickId(r)||bestId,version:`canonical-${version}`,canonical};
      }catch(e){
        fs.writeFileSync(`rubyclips/muffin_work/resolver-ep${epn}-canonical-${version}-error.txt`,String(e?.stack||e));
      }
    }
  }
  throw new Error(`Episode ${epn}: no downloadable video URL from any resolver`);
}

(async()=>{
  fs.mkdirSync('rubyclips/muffin_work',{recursive:true});
  const out=[];
  for(const ep of episodes){
    const got=await resolve(ep.url,ep.n);
    const file=`rubyclips/muffin_work/ep${ep.n}.mp4`;
    execFileSync('curl',['-L','--fail','--retry','2','--connect-timeout','20','-A','Mozilla/5.0','-e','https://www.tiktok.com/',got.media,'-o',file],{stdio:'inherit'});
    if(fs.statSync(file).size<100000) throw new Error(`Episode ${ep.n}: file too small`);
    out.push({episode:ep.n,sourceUrl:got.canonical||ep.url,videoId:got.id||null,resolver:got.version,file});
  }
  fs.writeFileSync('rubyclips/muffin_work/episodes.json',JSON.stringify(out,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
