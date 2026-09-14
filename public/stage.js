'use strict';
const params=new URLSearchParams(location.search),isCloud=params.get('renderer')==='cloud';
const nativeVideo=document.getElementById("nativeVideo");let nativeMode=false,nativeSource=null;
let state=null,player=null,ready=false,lastId=null,lastError=null;
const title=document.getElementById('gameTitle'),chat=document.getElementById('chat'),speech=document.getElementById('speech'),tap=document.getElementById('tap');
const avatarZone=document.getElementById('avatarZone');
const recentFollower=document.getElementById('recentFollower'),recentGift=document.getElementById('recentGift');let lastChatTs=0;
const avatarChat=document.querySelector('.avatarChat'),avatarDrink=document.querySelector('.avatarDrink'),avatarSnack=document.querySelector('.avatarSnack');let actionTimer=null;
window.__playerStatus={code:-999,label:'loading',position:0,error:null};
const labels={'-1':'unstarted','0':'ended','1':'playing','2':'paused','3':'buffering','5':'cued'};
function report(code,error=null){
  if(error)lastError=error;
  if(code===1)lastError=null;
  window.__playerStatus={code,label:lastError?'error':(labels[code]||'loading'),error:lastError,videoId:state?.current?.id,position:nativeMode?nativeVideo.currentTime:(ready?player.getCurrentTime():0)};
  if(lastError)title.textContent=lastError;
}
function say(text){speech.textContent=text;speech.classList.add('show');avatarZone.classList.remove('chatting','drinking','snacking');avatarZone.classList.add('reacting');clearTimeout(say.timer);say.timer=setTimeout(()=>{speech.classList.remove('show');avatarZone.classList.remove('reacting');},5200);}
function addLine(text,cls='chatLine'){const d=document.createElement('div');d.className=cls;d.textContent=text;chat.appendChild(d);while(chat.children.length>7)chat.firstChild.remove();}
function renderState(s){if(s.recentFollower)recentFollower.textContent='@'+s.recentFollower.user;if(s.recentGift)recentGift.textContent='@'+s.recentGift.user+' · '+s.recentGift.gift;for(const c of s.chat||[]){if(c.ts>lastChatTs){addLine('@'+c.user+': '+c.text);lastChatTs=c.ts}}}
function playAction(kind){if(avatarZone.classList.contains('reacting'))return;const video=kind==='drinking'?avatarDrink:kind==='snacking'?avatarSnack:avatarChat;if(!video)return;clearTimeout(actionTimer);avatarZone.classList.remove('chatting','drinking','snacking');avatarZone.classList.add(kind);video.currentTime=0;video.play().catch(()=>{});const done=()=>{avatarZone.classList.remove(kind);video.removeEventListener('ended',done)};video.addEventListener('ended',done);actionTimer=setTimeout(done,6500)}
function loadVideo(){
  if(state?.current?.sourceUrl){
    if(!nativeMode||nativeSource!==state.current.sourceUrl){nativeMode=true;nativeSource=state.current.sourceUrl;lastError=null;lastId=null;if(ready)player.pauseVideo();document.getElementById('yt').style.display='none';nativeVideo.style.display='block';nativeVideo.src=state.current.sourceUrl;nativeVideo.loop=!!state.current.test;nativeVideo.muted=!isCloud;nativeVideo.volume=.58;title.textContent=state.current.title;nativeVideo.play().catch(()=>{tap.style.display='flex';});}
    return;
  }
  if(nativeMode){nativeMode=false;nativeVideo.pause();nativeVideo.removeAttribute('src');nativeVideo.load();nativeVideo.style.display='none';document.getElementById('yt').style.display='block';lastId=null;}

  if(!ready||!state?.current?.id||lastId===state.current.id)return;
  lastId=state.current.id;lastError=null;
  title.textContent=state.current.title;
  player.mute();player.loadVideoById(lastId);
  if(!state.playing)player.pauseVideo();
}
window.onYouTubeIframeAPIReady=()=>{
  player=new YT.Player('yt',{width:'100%',height:'100%',playerVars:{origin:location.origin,autoplay:1,mute:1,controls:1,rel:0,fs:0,playsinline:1},events:{
    onReady:()=>{ready=true;loadVideo();},
    onStateChange:({data})=>{if(nativeMode)return;report(data);if(data===1){tap.style.display='none';if(isCloud){player.unMute();player.setVolume(58);}}},
    onError:({data})=>{if(nativeMode)return;const messages={2:'Invalid video ID',5:'YouTube playback failed',100:'Video unavailable',101:'Embedding disabled for this video',150:'Embedding disabled for this video',153:'YouTube rejected the player identification'};report(-data,(messages[data]||'YouTube playback error')+' (code '+data+')');tap.style.display='flex';},
    onAutoplayBlocked:()=>{if(nativeMode)return;tap.style.display='flex';report(-998,'Playback needs a start click');}
  }});
};
document.getElementById('tapBtn').onclick=()=>{if(nativeMode){nativeVideo.play().catch(()=>{});return;}if(ready){lastError=null;player.mute();player.playVideo();}};
async function update(){try{state=await(await fetch('/api/state',{cache:'no-store'})).json();renderState(state);loadVideo();}catch{title.textContent='Reconnecting to cloud service…';}}
// Register callbacks before loading YouTube; do not call player methods before onReady.
const apiScript=document.createElement('script');apiScript.src='https://www.youtube.com/iframe_api';apiScript.onerror=()=>report(-997,'YouTube player could not load');document.head.append(apiScript);
if(typeof io==='function'){
 const socket=io();socket.on('status',s=>{state=s;renderState(s);loadVideo();});socket.on('queue',s=>{state=s;renderState(s);loadVideo();});
 socket.on('playback',p=>{if(state)state.playing=p.playing;if(nativeMode){p.playing?nativeVideo.play().catch(()=>{}):nativeVideo.pause();}else if(ready)p.playing?player.playVideo():player.pauseVideo();});
 socket.on('chat',c=>{lastChatTs=Math.max(lastChatTs,c.ts||0);addLine('@'+c.user+': '+c.text);playAction('chatting')});socket.on('event',e=>{if(e.type==='commentary')say(e.text);else if(e.type==='follow'){recentFollower.textContent='@'+e.user;addLine(e.text,'eventLine');say('Thanks for the follow, '+e.user+'.');}else if(e.type==='gift'){recentGift.textContent='@'+e.user+' · '+e.gift;addLine(e.text,'eventLine');say('Thank you for the '+e.gift+', '+e.user+'.');}});
}
nativeVideo.addEventListener('playing',()=>{lastError=null;tap.style.display='none';report(1);});
nativeVideo.addEventListener('error',()=>report(-994,'Direct video playback failed: '+(nativeVideo.error?.message||'unknown error')));
setInterval(()=>{if(nativeMode)report(nativeVideo.ended?0:(nativeVideo.paused?2:(nativeVideo.readyState>=2&&!nativeVideo.seeking?1:3)));else if(ready)report(player.getPlayerState());},2000);
setTimeout(()=>{if(!ready&&!nativeMode)report(-996,'YouTube did not finish loading');},30000);
setInterval(update,15000);update();
setTimeout(()=>playAction('drinking'),75000);setInterval(()=>playAction('drinking'),420000);setTimeout(()=>playAction('snacking'),210000);setInterval(()=>playAction('snacking'),600000);