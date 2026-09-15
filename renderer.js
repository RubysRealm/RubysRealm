import {spawn} from 'node:child_process';
import fs from 'node:fs';
const port=process.env.PORT||10000;
const local=`http://127.0.0.1:${port}`;
const headers={'Content-Type':'application/json','x-control-token':process.env.CONTROL_TOKEN||'change-me'};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function post(path,data){const r=await fetch(local+path,{method:'POST',headers,body:JSON.stringify(data)});if(!r.ok)throw new Error(`POST ${path} failed ${r.status}`);return r;}
async function getState(){return await(await fetch(local+'/api/state',{cache:'no-store'})).json();}
let stopping=false,dl=null,player=null,audioDec=null,audioOut=null,currentId=null,startedAt=0,pausedAt=0,totalPaused=0,lastReported='',shotBusy=false;
process.on('SIGTERM',()=>{stopping=true;stopCurrent();});
process.on('SIGINT',()=>{stopping=true;stopCurrent();});
function stopCurrent(){for(const p of [dl,player,audioDec,audioOut]){try{p?.kill('SIGTERM')}catch{}}dl=null;player=null;audioDec=null;audioOut=null;currentId=null;}
async function report(label,error=null){if(!currentId)return;const pos=startedAt?Math.max(0,Math.floor((Date.now()-startedAt-totalPaused-(pausedAt?Date.now()-pausedAt:0))/1000)):0;const key=`${label}|${error||''}`;if(key!==lastReported){console.log('Cloud playback:',JSON.stringify({label,error,videoId:currentId,position:pos}));lastReported=key;}await post('/api/player-state',{renderer:'cloud',code:label==='playing'?1:label==='paused'?2:label==='buffering'?3:-1,label,error,videoId:currentId,position:pos}).catch(()=>{});}
function screenshot(){if(shotBusy)return;shotBusy=true;const p=spawn('ffmpeg',['-hide_banner','-loglevel','error','-f','x11grab','-video_size',`${process.env.STREAM_WIDTH||720}x${process.env.STREAM_HEIGHT||1280}`,'-i',':99.0','-frames:v','1','-y','/tmp/cloud-frame-next.jpg']);p.on('exit',()=>{try{fs.renameSync('/tmp/cloud-frame-next.jpg','/tmp/cloud-frame.jpg')}catch{}shotBusy=false});p.on('error',()=>{shotBusy=false});}
function startVideo(id){return new Promise((resolve)=>{
 currentId=id;startedAt=Date.now();pausedAt=0;totalPaused=0;lastReported='';
 console.log('Starting direct gameplay',id);
 const yargs=['--no-playlist','--no-warnings','--retries','20','--fragment-retries','20','--retry-sleep','fragment:2','--extractor-args','youtube:player_client=android_vr,web_safari','-f','18/best[ext=mp4][vcodec^=avc1][acodec!=none][height<=720]/best[ext=mp4][acodec!=none][height<=720]/best[height<=720]','-o','-',`https://www.youtube.com/watch?v=${id}`];
 dl=spawn('yt-dlp',yargs,{stdio:['ignore','pipe','pipe']});
 player=spawn('ffplay',['-hide_banner','-loglevel','warning','-autoexit','-an','-fs','-noborder','-i','pipe:0'],{stdio:['pipe','ignore','pipe'],env:{...process.env,SDL_AUDIODRIVER:'dummy'}});
 audioDec=spawn('ffmpeg',['-hide_banner','-loglevel','error','-i','pipe:0','-vn','-f','s16le','-ar','44100','-ac','2','pipe:1'],{stdio:['pipe','pipe','pipe']});
 audioOut=spawn('paplay',['--device=takarada','--raw','--format=s16le','--rate=44100','--channels=2'],{stdio:['pipe','ignore','pipe']});
 dl.stdout.pipe(player.stdin);dl.stdout.pipe(audioDec.stdin);audioDec.stdout.pipe(audioOut.stdin);
 let yerr='',perr='',aerr='',done=false;
 const finish=async(kind,code)=>{if(done)return;done=true;try{dl?.stdout?.unpipe(player?.stdin);dl?.stdout?.unpipe(audioDec?.stdin)}catch{};for(const p of [dl,player,audioDec,audioOut]){try{p?.kill('SIGTERM')}catch{}}const same=currentId===id;dl=null;player=null;audioDec=null;audioOut=null;if(!same)return resolve({ended:false});if(stopping)return resolve({ended:false});if(kind==='player'&&code===0){await report('ended');currentId=null;return resolve({ended:true});}const msg=(kind==='yt-dlp'?yerr:kind==='player'?perr:aerr).trim().slice(-700)||`${kind} exited ${code}`;await report('error',msg);currentId=null;resolve({ended:false,error:msg});};
 dl.stderr.on('data',d=>{yerr=(yerr+String(d)).slice(-4000)});player.stderr.on('data',d=>{perr=(perr+String(d)).slice(-4000)});audioDec.stderr.on('data',d=>{aerr=(aerr+String(d)).slice(-4000)});audioOut.stderr.on('data',d=>{aerr=(aerr+String(d)).slice(-4000)});
 dl.on('error',e=>{yerr=e.message;finish('yt-dlp',-1)});player.on('error',e=>{perr=e.message;finish('player',-1)});audioDec.on('error',e=>{aerr=e.message;finish('audio',-1)});audioOut.on('error',e=>{aerr=e.message;finish('audio',-1)});
 dl.on('exit',c=>{if(c&&c!==0)finish('yt-dlp',c)});player.on('exit',c=>finish('player',c));audioDec.on('exit',c=>{if(c&&c!==0)finish('audio',c)});audioOut.on('exit',c=>{if(c&&c!==0)finish('audio',c)});
 setTimeout(()=>{if(currentId===id&&player&&!player.killed)report('playing').catch(()=>{});},9000);
 });}
for(let i=0;i<60;i++){try{if((await fetch(local+'/api/state')).ok)break;}catch{}await pause(1000);}
console.log('Cloud renderer: direct yt-dlp gameplay + PulseAudio original audio');
let lastPlaying=true;
while(!stopping){
 try{
  const st=await getState();const wanted=st.current?.id;
  if(wanted&&wanted!==currentId){stopCurrent();await pause(500);startVideo(wanted).then(async r=>{if(r.ended)await post('/api/video-ended',{videoId:wanted}).catch(()=>{});});}
  if(currentId&&st.playing!==lastPlaying){if(st.playing){for(const p of [dl,player,audioDec,audioOut])try{p?.kill('SIGCONT')}catch{};if(pausedAt){totalPaused+=Date.now()-pausedAt;pausedAt=0;}await report('playing');}else{for(const p of [dl,player,audioDec,audioOut])try{p?.kill('SIGSTOP')}catch{};pausedAt=Date.now();await report('paused');}lastPlaying=st.playing;}
  if(currentId&&st.playing&&startedAt)await report('playing');
  screenshot();
 }catch(e){console.log('renderer loop error',e.message);}
 await pause(5000);
}
stopCurrent();
