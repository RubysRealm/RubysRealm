import {chromium} from 'playwright';
import fs from 'node:fs';
const port=process.env.PORT||10000;
const local=`http://127.0.0.1:${port}`;
const origin=process.env.RENDER_EXTERNAL_URL||local;
const headers={'Content-Type':'application/json','x-control-token':process.env.CONTROL_TOKEN||'change-me'};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function post(path,data){const r=await fetch(local+path,{method:'POST',headers,body:JSON.stringify(data)});if(!r.ok)throw new Error('Renderer report failed: '+r.status);return r;}
async function getState(){return await(await fetch(local+'/api/state',{cache:'no-store'})).json();}
let stopping=false,browser;
process.on('SIGTERM',()=>{stopping=true;browser?.close();});
for(let i=0;i<60;i++){try{if((await fetch(local+'/api/state')).ok)break;}catch{}await pause(1000);}

const layoutCss=`
html,body{margin:0!important;padding:0!important;width:100vw!important;height:100vh!important;overflow:hidden!important;background:#000!important}
ytd-masthead,#masthead-container,#secondary,#below,#comments,#chat-container,#panels,#related,#meta,#info,#description,#columns>#secondary,#guide,#guide-content,.ytd-watch-flexy[hidden],tp-yt-app-drawer{display:none!important}
#columns,#primary,#primary-inner,#player-container-outer,#player-container-inner,#player,#movie_player{margin:0!important;padding:0!important;max-width:none!important;min-width:0!important}
#movie_player{position:fixed!important;left:0!important;top:36vh!important;width:100vw!important;height:64vh!important;z-index:2147483000!important;background:#000!important}
#movie_player .html5-video-container{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;background:#000!important}
#movie_player video.html5-main-video{position:absolute!important;left:0!important;top:0!important;width:100%!important;height:100%!important;object-fit:cover!important;background:#000!important}
.ytp-chrome-bottom,.ytp-chrome-top,.ytp-gradient-bottom,.ytp-gradient-top,.ytp-title,.ytp-title-channel,.ytp-watermark,.ytp-ce-element,.ytp-cards-button,.ytp-pause-overlay,.ytp-spinner,.ytp-ad-overlay-container,.ytp-ad-player-overlay{display:none!important;opacity:0!important}
#takaradaOverlayHost{position:fixed!important;left:0!important;top:0!important;width:100vw!important;height:36vh!important;overflow:hidden!important;z-index:2147483646!important;background:#0e0d18!important;pointer-events:none!important}
#takaradaOverlayFrame{position:absolute!important;left:0!important;top:0!important;width:100vw!important;height:36vh!important;border:0!important;background:#0e0d18!important}
`;

async function installLayout(page){
 try{await page.addStyleTag({content:layoutCss});}catch{}
 await page.evaluate((src)=>{
  let host=document.getElementById('takaradaOverlayHost');
  if(!host){host=document.createElement('div');host.id='takaradaOverlayHost';const f=document.createElement('iframe');f.id='takaradaOverlayFrame';f.src=src;f.setAttribute('allow','autoplay');host.appendChild(f);document.documentElement.appendChild(host);}
  document.documentElement.style.background='#000';document.body&&(document.body.style.background='#000');
 },origin+'/avatar-overlay.html?performance=engine').catch(()=>{});
}

async function clickConsent(page){
 for(const text of ['Reject all','Accept all','I agree']){const b=page.getByRole('button',{name:text,exact:false}).first();if(await b.isVisible().catch(()=>false)){await b.click().catch(()=>{});await pause(800);break;}}
}
async function skipAd(page){
 const ad=await page.evaluate(()=>document.getElementById('movie_player')?.classList.contains('ad-showing')||false).catch(()=>false);
 if(!ad)return false;
 for(const sel of ['.ytp-ad-skip-button','.ytp-skip-ad-button','.ytp-ad-skip-button-modern','.ytp-ad-skip-button-container button']){const b=page.locator(sel).first();if(await b.isVisible().catch(()=>false)){await b.click().catch(()=>{});return true;}}
 await page.evaluate(()=>{const v=document.querySelector('video');if(v&&Number.isFinite(v.duration)&&v.duration>0&&v.duration<180)v.currentTime=Math.max(0,v.duration-.15)}).catch(()=>{});return true;
}
async function playWatch(page,id){
 const url=`https://www.youtube.com/watch?v=${encodeURIComponent(id)}&autoplay=1`;
 await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
 await clickConsent(page);await installLayout(page);
 await page.waitForSelector('video',{timeout:30000}).catch(()=>{});
 await page.evaluate(()=>{const v=document.querySelector('video');if(v){v.muted=false;v.volume=.58;v.play().catch(()=>{});}}).catch(()=>{});
}
async function playerSnapshot(page,id){
 return await page.evaluate((videoId)=>{
  const v=document.querySelector('video'),p=document.getElementById('movie_player');
  if(!v)return{code:-1,label:'loading',error:'YouTube watch video element not ready',videoId,position:0};
  const ad=!!p?.classList.contains('ad-showing');let code,label;
  if(v.error){code=-1;label='error'}else if(v.ended){code=0;label='ended'}else if(v.paused){code=2;label='paused'}else if(v.readyState<2){code=3;label='buffering'}else{code=1;label='playing'}
  return{code,label,error:v.error?.message||null,videoId,position:Number(v.currentTime||0),duration:Number.isFinite(v.duration)?Number(v.duration):0,ad};
 },id).catch(e=>({code:-1,label:'error',error:e.message,videoId:id,position:0}));
}

while(!stopping){
 try{
  browser=await chromium.launch({executablePath:'/usr/bin/google-chrome-stable',headless:false,args:['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required','--kiosk','--window-position=0,0',`--window-size=${process.env.STREAM_WIDTH||720},${process.env.STREAM_HEIGHT||1280}`,'--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
  const context=await browser.newContext({viewport:{width:Number(process.env.STREAM_WIDTH||720),height:Number(process.env.STREAM_HEIGHT||1280)},bypassCSP:true});
  await context.route('**/*',route=>{const u=route.request().url();if(/doubleclick\.net|googlesyndication\.com|googleadservices\.com|pagead2\.googlesyndication\.com/i.test(u))return route.abort();return route.continue();});
  const page=await context.newPage();page.on('pageerror',e=>console.log('Renderer page error:',e.message));
  let currentId=null,endedId=null,lastLabel=null;
  console.log('Cloud renderer: direct YouTube watch compositor');
  while(!stopping&&!page.isClosed()){
   const st=await getState();const wanted=st.current?.id;
   if(wanted&&wanted!==currentId){currentId=wanted;endedId=null;await playWatch(page,currentId);}
   await installLayout(page);await skipAd(page);
   let s=await playerSnapshot(page,currentId);
   if(s.label==='paused'&&!s.ad){await page.evaluate(()=>document.querySelector('video')?.play().catch(()=>{})).catch(()=>{});await pause(250);s=await playerSnapshot(page,currentId);}
   if(s.label!==lastLabel){console.log('Cloud playback:',JSON.stringify(s));lastLabel=s.label;}
   await post('/api/player-state',{...s,renderer:'cloud'});
   if(s.label==='ended'&&s.videoId&&s.videoId!==endedId){endedId=s.videoId;await post('/api/video-ended',{videoId:s.videoId});}
   if(s.label==='playing')endedId=null;
   await page.screenshot({path:'/tmp/cloud-frame-next.jpg',type:'jpeg',quality:78});fs.renameSync('/tmp/cloud-frame-next.jpg','/tmp/cloud-frame.jpg');
   await pause(5000);
  }
 }catch(e){console.log('Cloud renderer stopped:',e.message);await post('/api/player-state',{renderer:'cloud',code:-995,label:'error',error:e.message}).catch(()=>{});}
 await browser?.close().catch(()=>{});if(!stopping)await pause(8000);
}
