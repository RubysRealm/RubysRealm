'use strict';
const params=new URLSearchParams(location.search),isCloud=params.get('renderer')==='cloud';
const nativeVideo=document.getElementById('nativeVideo'),yt=document.getElementById('yt'),tap=document.getElementById('tap'),status=document.getElementById('status');
let state=null,player=null,ready=false,lastId=null,nativeMode=false,nativeSource=null,lastError=null;
window.__playerStatus={code:-999,label:'loading',position:0,error:null};
const labels={'-1':'unstarted','0':'ended','1':'playing','2':'paused','3':'buffering','5':'cued'};
function showStatus(text,sticky=false){status.textContent=text||'';status.classList.toggle('show',!!text);clearTimeout(showStatus.t);if(text&&!sticky)showStatus.t=setTimeout(()=>status.classList.remove('show'),2500)}
function report(code,error=null){if(error)lastError=error;if(code===1)lastError=null;window.__playerStatus={code,label:lastError?'error':(labels[code]||'loading'),error:lastError,videoId:state?.current?.id,position:nativeMode?Number(nativeVideo.currentTime||0):(ready?Number(player.getCurrentTime()||0):0)};if(error)showStatus(error,true)}
function loadVideo(){
 if(!state?.current)return;
 if(state.current.sourceUrl){
  if(!nativeMode||nativeSource!==state.current.sourceUrl){nativeMode=true;nativeSource=state.current.sourceUrl;lastId=null;lastError=null;yt.style.display='none';nativeVideo.style.display='block';nativeVideo.src=nativeSource;nativeVideo.loop=!!state.current.test;nativeVideo.muted=false;nativeVideo.volume=1;nativeVideo.play().catch(()=>tap.style.display='flex');}
  if(!state.playing)nativeVideo.pause();return;
 }
 if(nativeMode){nativeMode=false;nativeSource=null;nativeVideo.pause();nativeVideo.removeAttribute('src');nativeVideo.load();nativeVideo.style.display='none';yt.style.display='block';}
 if(!ready||!state.current.id||lastId===state.current.id)return;
 lastId=state.current.id;lastError=null;player.loadVideoById(lastId);if(state.playing){player.unMute();player.setVolume(100);player.playVideo();}else player.pauseVideo();
}
window.onYouTubeIframeAPIReady=()=>{player=new YT.Player('yt',{width:'100%',height:'100%',playerVars:{origin:location.origin,autoplay:1,mute:0,controls:1,rel:0,fs:1,playsinline:1},events:{onReady:()=>{ready=true;loadVideo();},onStateChange:({data})=>{if(nativeMode)return;report(data);if(data===1){tap.style.display='none';player.unMute();player.setVolume(100);}},onError:({data})=>{if(nativeMode)return;const m={2:'Invalid video',5:'Playback failed',100:'Video unavailable',101:'YouTube embedding is disabled',150:'YouTube embedding is disabled',153:'YouTube rejected the embedded player'};report(-data,(m[data]||'YouTube playback error')+' (code '+data+')');tap.style.display='flex';},onAutoplayBlocked:()=>{tap.style.display='flex';showStatus('Tap once to enable gameplay audio',true);}}});};
document.getElementById('tapBtn').onclick=()=>{lastError=null;status.classList.remove('show');tap.style.display='none';if(nativeMode){nativeVideo.muted=false;nativeVideo.volume=1;nativeVideo.play().catch(()=>tap.style.display='flex');}else if(ready){player.unMute();player.setVolume(100);player.playVideo();}};
async function update(){try{state=await(await fetch('/api/state',{cache:'no-store'})).json();loadVideo();}catch{showStatus('Reconnecting…',true)}}
const api=document.createElement('script');api.src='https://www.youtube.com/iframe_api';api.onerror=()=>report(-997,'YouTube player could not load');document.head.append(api);
if(typeof io==='function'){const socket=io();socket.on('status',s=>{state=s;loadVideo();});socket.on('queue',s=>{state=s;lastId=null;loadVideo();});socket.on('playback',p=>{if(state)state.playing=p.playing;if(nativeMode){p.playing?nativeVideo.play().catch(()=>{}):nativeVideo.pause();}else if(ready)p.playing?player.playVideo():player.pauseVideo();});}
nativeVideo.addEventListener('playing',()=>{lastError=null;tap.style.display='none';report(1)});nativeVideo.addEventListener('ended',()=>report(0));nativeVideo.addEventListener('error',()=>report(-994,'Direct gameplay playback failed'));
setInterval(()=>{if(nativeMode)report(nativeVideo.ended?0:(nativeVideo.paused?2:(nativeVideo.readyState>=2&&!nativeVideo.seeking?1:3)));else if(ready)report(player.getPlayerState());},2000);
setInterval(update,15000);update();