import {spawn} from 'node:child_process';
import {createTikTokLive,endTikTokLive,streamlabsConfigured} from './streamlabs-tiktok.js';

const port=process.env.PORT||10000;
const local=`http://127.0.0.1:${port}`;
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const title=process.env.TIKTOK_LIVE_TITLE||'Relaxing Minecraft Longplay';
const category=process.env.TIKTOK_LIVE_CATEGORY||'';
const enabled=(process.env.AUTO_TIKTOK_LIVE||'false').toLowerCase()==='true';
let room=null,ffmpeg=null,stopping=false;

async function state(){
  const r=await fetch(local+'/api/state',{cache:'no-store'});
  if(!r.ok) throw new Error(`state ${r.status}`);
  return await r.json();
}
function redact(s=''){
  return String(s).replace(/rtmps?:\/\/\S+/gi,'[TikTok destination]').slice(-600);
}
async function endRoom(){
  const r=room;room=null;
  if(r?.id){try{await endTikTokLive(r.id);}catch(e){console.log('TikTok room end error',redact(e.message));}}
}
function stopEncoder(){
  if(ffmpeg){try{ffmpeg.kill('SIGTERM')}catch{};ffmpeg=null;}
}
async function shutdown(){
  if(stopping)return;stopping=true;stopEncoder();await endRoom();process.exit(0);
}
process.on('SIGTERM',shutdown);process.on('SIGINT',shutdown);

async function startEncoder(){
  room=await createTikTokLive({title,category,audienceType:'0'});
  console.log('TikTok LIVE room created by cloud controller');
  const w=process.env.STREAM_WIDTH||'720',h=process.env.STREAM_HEIGHT||'1280',fps=process.env.STREAM_FPS||'30';
  const args=['-hide_banner','-loglevel','warning','-thread_queue_size','1024','-f','x11grab','-draw_mouse','0','-framerate',fps,'-video_size',`${w}x${h}`,'-i',':99.0','-thread_queue_size','1024','-f','pulse','-i','takarada.monitor','-c:v','libx264','-preset','veryfast','-tune','zerolatency','-pix_fmt','yuv420p','-b:v','3500k','-maxrate','4000k','-bufsize','7000k','-g',String(Number(fps)*2),'-c:a','aac','-b:a','160k','-ar','44100','-f','flv',room.destination];
  ffmpeg=spawn('ffmpeg',args,{stdio:['ignore','ignore','pipe']});
  let err='';
  ffmpeg.stderr.on('data',d=>err=(err+String(d)).slice(-4000));
  ffmpeg.on('spawn',()=>console.log('Autonomous TikTok encoder started'));
  ffmpeg.on('exit',async code=>{
    const wasStopping=stopping;ffmpeg=null;
    if(code&&!wasStopping)console.log('Autonomous TikTok encoder exited',code,redact(err));
    await endRoom();
  });
  ffmpeg.on('error',e=>console.log('Autonomous TikTok encoder error',redact(e.message)));
}

for(let i=0;i<90&&!stopping;i++){
  try{if((await fetch(local+'/api/state')).ok)break;}catch{}
  await pause(1000);
}

if(!enabled){console.log('Autonomous TikTok LIVE sidecar ready; AUTO_TIKTOK_LIVE is disabled.');while(!stopping)await pause(60000);}
if(!streamlabsConfigured()){console.log('Autonomous TikTok LIVE waiting for one-time Streamlabs/TikTok authorization token.');while(!stopping)await pause(60000);}

console.log('Autonomous TikTok LIVE controller armed.');
while(!stopping){
  try{
    const s=await state();
    const fresh=s.cloudPlayerState?.label==='playing' && Date.now()-(s.cloudPlayerState.updatedAt||0)<20000;
    if(fresh&&!ffmpeg&&!room){try{await startEncoder();}catch(e){console.log('TikTok LIVE start error',redact(e.message));await endRoom();}}
    if(!fresh&&ffmpeg){console.log('Gameplay stopped; ending TikTok LIVE until playback is healthy again.');stopEncoder();await endRoom();}
  }catch(e){console.log('Autolive controller error',redact(e.message));}
  await pause(ffmpeg?10000:15000);
}
