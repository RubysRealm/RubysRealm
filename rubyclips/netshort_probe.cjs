const fs = require('fs');
const { execFileSync } = require('child_process');
const puppeteer = require('puppeteer-core');

const url='https://netshort.com/episode/the-counterattack-of-the-fat-wife-queen-2092170996947619841-ep-40';
const chrome=['/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'].find(p=>fs.existsSync(p));
if(!chrome) throw new Error('Chrome not found');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const candidates=[];
function add(u,why){const s=String(u||'');if(!s||s.startsWith('blob:')||s.startsWith('data:'))return;if(!candidates.some(x=>x.url===s))candidates.push({url:s,why});}
(async()=>{
 const browser=await puppeteer.launch({headless:true,executablePath:chrome,args:['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required','--disable-blink-features=AutomationControlled']});
 try{
  const page=await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36');
  page.on('request',req=>{const u=req.url();if(req.resourceType()==='media'||/m3u8|\.mp4|play|vod|video/i.test(u))add(u,'request:'+req.resourceType());});
  page.on('response',resp=>{const u=resp.url(),h=resp.headers()||{},ct=String(h['content-type']||'').toLowerCase();if(ct.startsWith('video/')||ct.includes('mpegurl')||/m3u8|\.mp4|play|vod|video/i.test(u))add(u,'response:'+ct);});
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
  await sleep(2500);
  const before=await page.evaluate(()=>{const v=document.querySelector('video');return {src:v?.src||'',currentSrc:v?.currentSrc||'',readyState:v?.readyState||0,duration:v?.duration||0,outer:v?.outerHTML||''};});
  console.log('VIDEO_BEFORE',JSON.stringify(before));
  await page.evaluate(async()=>{const v=document.querySelector('video');if(v){v.muted=true;try{await v.play();}catch(e){console.log('play-error',String(e));}}});
  await sleep(7000);
  const after=await page.evaluate(()=>{const v=document.querySelector('video');return {src:v?.src||'',currentSrc:v?.currentSrc||'',readyState:v?.readyState||0,duration:v?.duration||0,outer:v?.outerHTML||'',resources:performance.getEntriesByType('resource').map(x=>x.name).filter(x=>/m3u8|\.mp4|play|vod|video/i.test(x))};});
  console.log('VIDEO_AFTER',JSON.stringify(after));
  for(const r of after.resources||[])add(r,'performance');
  console.log('CANDIDATES',JSON.stringify(candidates,null,2));
  fs.writeFileSync('rubyclips/netshort_probe.json',JSON.stringify({before,after,candidates},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
