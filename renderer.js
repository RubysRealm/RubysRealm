import {chromium} from 'playwright';
import fs from 'node:fs';
const port=process.env.PORT||10000;
const local=`http://127.0.0.1:${port}`;
const origin=process.env.RENDER_EXTERNAL_URL||local;
const headers={'Content-Type':'application/json','x-control-token':process.env.CONTROL_TOKEN||'change-me'};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function post(path,data){const r=await fetch(local+path,{method:'POST',headers,body:JSON.stringify(data)});if(!r.ok)throw new Error('Renderer report failed: '+r.status);}
let stopping=false,browser;
process.on('SIGTERM',()=>{stopping=true;browser?.close();});
for(let i=0;i<60;i++){try{if((await fetch(local+'/api/state')).ok)break;}catch{}await pause(1000);}
while(!stopping){
 try{
  browser=await chromium.launch({executablePath:'/usr/bin/google-chrome-stable',headless:false,args:['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required','--kiosk','--window-position=0,0',`--window-size=${process.env.STREAM_WIDTH||720},${process.env.STREAM_HEIGHT||1280}`,'--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
  const page=await browser.newPage({viewport:{width:Number(process.env.STREAM_WIDTH||720),height:Number(process.env.STREAM_HEIGHT||1280)}});
  page.on('pageerror',e=>console.log('Stage script error:',e.message));page.on('console',m=>{if(m.type()==='error')console.log('Stage console error:',m.text());});
  await page.goto(origin+'/stage?renderer=cloud',{waitUntil:'domcontentloaded',timeout:60000});console.log('Cloud renderer: Google Chrome with full media codecs');
  let endedId=null,lastLabel=null,clicked=false;
  while(!stopping&&!page.isClosed()){
   const s=await page.evaluate(()=>window.__playerStatus||{code:-999,label:'loading'});
   if(s.label!==lastLabel){console.log('Cloud playback:',JSON.stringify(s));lastLabel=s.label;}
   if(s.label==='error'||s.label==='unstarted'){const frames=page.frames().filter(f=>f.url().includes('youtube.com/embed'));s.diagnostic=(await Promise.all(frames.map(f=>f.locator('body').innerText({timeout:3000}).catch(()=>'')))).join(' ').slice(0,1500);}
   await post('/api/player-state',{...s,renderer:'cloud'});
   if(s.label==='ended'&&s.videoId&&s.videoId!==endedId){endedId=s.videoId;await post('/api/video-ended',{videoId:s.videoId});}
   if(s.label==='playing'){endedId=null;clicked=false;}
   if(!clicked&&await page.locator('#tapBtn').isVisible()){await page.locator('#tapBtn').click();clicked=true;}
   await page.screenshot({path:'/tmp/cloud-frame-next.jpg',type:'jpeg',quality:76});fs.renameSync('/tmp/cloud-frame-next.jpg','/tmp/cloud-frame.jpg');
   await pause(5000);
  }
 }catch(e){console.log('Cloud renderer stopped:',e.message);await post('/api/player-state',{renderer:'cloud',code:-995,label:'error',error:e.message}).catch(()=>{});}
 await browser?.close().catch(()=>{});if(!stopping)await pause(10000);
}
