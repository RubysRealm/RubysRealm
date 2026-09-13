const fs=require('fs');
const {execFileSync}=require('child_process');
const Tiktok=require('@tobyg74/tiktok-api-dl');

const episodes=[
  {n:1,url:'https://www.tiktok.com/@muffindrama_us/video/7682997000391904526'},
  {n:2,url:'https://www.tiktok.com/shortdrama/episode/7682993954661553173/2'},
  {n:3,url:'https://www.tiktok.com/shortdrama/episode/7682993954661553173/3'},
  {n:4,url:'https://www.tiktok.com/shortdrama/episode/7682993954661553173/4'}
];

(async()=>{
  fs.mkdirSync('rubyclips/muffin_work',{recursive:true});
  const out=[];
  for(const ep of episodes){
    const r=await Tiktok.Downloader(ep.url,{version:'v2'});
    fs.writeFileSync(`rubyclips/muffin_work/resolver-ep${ep.n}.json`,JSON.stringify(r,null,2));
    const media=r?.result?.video?.playAddr?.[0];
    const id=String(r?.result?.id||r?.result?.video?.id||'').trim();
    if(!media) throw new Error(`Episode ${ep.n}: no playAddr`);
    const file=`rubyclips/muffin_work/ep${ep.n}.mp4`;
    execFileSync('curl',['-L','--fail','--retry','2','-A','Mozilla/5.0','-e','https://www.tiktok.com/',media,'-o',file],{stdio:'inherit'});
    if(fs.statSync(file).size<100000) throw new Error(`Episode ${ep.n}: file too small`);
    out.push({episode:ep.n,sourceUrl:ep.url,videoId:id||null,file});
  }
  fs.writeFileSync('rubyclips/muffin_work/episodes.json',JSON.stringify(out,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
