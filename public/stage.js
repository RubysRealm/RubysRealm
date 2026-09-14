'use strict';
const params=new URLSearchParams(location.search),isCloud=params.get('renderer')==='cloud';
let state=null,player=null,ready=false,lastId=null,lastError=null;
const title=document.getElementById('gameTitle'),chat=document.getElementById('chat'),speech=document.getElementById('speech'),tap=document.getElementById('tap');
window.__playerStatus={code:-999,label:'loading',position:0,error:null};
const labels={'-1':'unstarted','0':'ended','1':'playing','2':'paused','3':'buffering','5':'cued'};
function report(code,error=null){
  if(error)lastError=error;
  if(code===1)lastError=null;
  window.__playerStatus={code,label:lastError?'error':(labels[code]||'loading'),error:lastError,videoId:state?.current?.id,position:ready?player.getCurrentTime():0};
  if(lastError)title.textContent=lastError;
}
function say(text){speech.textContent=text;speech.classList.add('show');clearTimeout(say.timer);say.timer=setTimeout(()=>speech.classList.remove('show'),5200);}
function addLine(text,cls='chatLine'){const d=document.createElement('div');d.className=cls;d.textContent=text;chat.appendChild(d);while(chat.children.length>7)chat.firstChild.remove();}
function loadVideo(){
  if(!ready||!state?.current?.id||lastId===state.current.id)return;
  lastId=state.current.id;lastError=null;
  title.textContent=state.current.title;
  player.mute();player.loadVideoById(lastId);
  if(!state.playing)player.pauseVideo();
}
window.onYouTubeIframeAPIReady=()=>{
  player=new YT.Player('yt',{width:'100%',height:'100%',playerVars:{origin:location.origin,autoplay:1,mute:1,controls:1,rel:0,fs:0,playsinline:1},events:{
    onReady:()=>{ready=true;loadVideo();},
    onStateChange:({data})=>{report(data);if(data===1){tap.style.display='none';if(isCloud){player.unMute();player.setVolume(58);}}},
    onError:({data})=>{const messages={2:'Invalid video ID',5:'YouTube playback failed',100:'Video unavailable',101:'Embedding disabled for this video',150:'Embedding disabled for this video',153:'YouTube rejected the player identification'};report(-data,(messages[data]||'YouTube playback error')+' (code '+data+')');tap.style.display='flex';},
    onAutoplayBlocked:()=>{tap.style.display='flex';report(-998,'Playback needs a start click');}
  }});
};
document.getElementById('tapBtn').onclick=()=>{if(ready){lastError=null;player.mute();player.playVideo();}};
async function update(){try{state=await(await fetch('/api/state',{cache:'no-store'})).json();loadVideo();}catch{title.textContent='Reconnecting to cloud service…';}}
// Register callbacks before loading YouTube; do not call player methods before onReady.
const apiScript=document.createElement('script');apiScript.src='https://www.youtube.com/iframe_api';apiScript.onerror=()=>report(-997,'YouTube player could not load');document.head.append(apiScript);
if(typeof io==='function'){
 const socket=io();socket.on('status',s=>{state=s;loadVideo();});socket.on('queue',s=>{state=s;loadVideo();});
 socket.on('playback',p=>{if(state)state.playing=p.playing;if(ready)p.playing?player.playVideo():player.pauseVideo();});
 socket.on('chat',c=>addLine(c.user+': '+c.text));socket.on('event',e=>{if(e.type==='commentary')say(e.text);else if(e.type==='follow'||e.type==='gift'){addLine(e.text,'eventLine');say(e.type==='follow'?'Thanks for the follow.':'Thank you for the gift.');}});
}
setInterval(()=>{if(ready)report(player.getPlayerState());},2000);
setTimeout(()=>{if(!ready)report(-996,'YouTube did not finish loading');},30000);
setInterval(update,15000);update();
