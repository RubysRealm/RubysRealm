'use strict';
(()=>{
  const params=new URLSearchParams(location.search);
  if(params.get('performance')!=='locked') return;
  const avatarZone=document.getElementById('avatarZone');
  if(!avatarZone) return;

  const idle=document.querySelector('.avatarIdle');
  const talking=document.querySelector('.avatarTalking');
  const chatClip=document.querySelector('.avatarChat');
  const drinkClip=document.querySelector('.avatarDrink');
  const snackClip=document.querySelector('.avatarSnack');
  const all=[idle,talking,chatClip,drinkClip,snackClip].filter(Boolean);
  const speech=document.getElementById('speech');
  const chat=document.getElementById('chat');
  const recentFollower=document.getElementById('recentFollower');
  const recentGift=document.getElementById('recentGift');

  const style=document.createElement('style');
  style.textContent=`
    #avatarZone.lockedPreview .avatarVideo{display:block!important;opacity:0!important;transition:opacity .55s ease,transform 6s ease!important;transform:scale(1.025);filter:none!important}
    #avatarZone.lockedPreview .avatarVideo.lockedVisible{opacity:1!important}
    #avatarZone.lockedPreview.microLean .lockedVisible{transform:scale(1.045) translate(-.18%,.12%)}
    #avatarZone.lockedPreview.microLean2 .lockedVisible{transform:scale(1.038) translate(.18%,-.08%)}
    #lockedStart{position:absolute;inset:0;z-index:30;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.42)}
    #lockedStart button{border:0;border-radius:999px;background:#ff1744;color:#fff;font-size:1.65vh;font-weight:900;padding:1.35vh 2vh;box-shadow:0 8px 30px rgba(0,0,0,.48)}
    #lockedBadge{position:absolute;left:3%;top:19%;z-index:10;background:rgba(0,0,0,.52);border:1px solid rgba(255,255,255,.18);border-radius:999px;padding:.45vh .75vh;font-size:1.05vh;font-weight:800;opacity:.75}
  `;
  document.head.appendChild(style);
  avatarZone.classList.add('lockedPreview');

  for(const v of all){
    try{v.pause();v.loop=false;v.autoplay=false;v.removeAttribute('loop');v.removeAttribute('autoplay');v.currentTime=0;}catch{}
  }

  const badge=document.createElement('div');badge.id='lockedBadge';badge.textContent='TAKARADA • MINECRAFT';avatarZone.appendChild(badge);
  const start=document.createElement('div');start.id='lockedStart';
  const btn=document.createElement('button');btn.textContent='▶ START TAKARADA PREVIEW';start.appendChild(btn);avatarZone.appendChild(start);

  let idleLoopTimer=null,leanTimer=null,running=false,speaking=false;
  const timers=[];
  const later=(ms,fn)=>{const t=setTimeout(fn,ms);timers.push(t);return t;};

  function visible(v){
    for(const x of all)x.classList.remove('lockedVisible');
    if(v)v.classList.add('lockedVisible');
  }
  function play(v,rate=.78,restart=true,loop=false){
    if(!v)return;
    for(const x of all){if(x!==v){try{x.pause();}catch{}}}
    visible(v);v.loop=loop;v.playbackRate=rate;
    try{if(restart||v.ended||v.currentTime>Math.max(.1,(v.duration||1)-.25))v.currentTime=0;v.play().catch(()=>{});}catch{}
  }
  function addLine(text,cls='chatLine'){
    if(!chat)return;const d=document.createElement('div');d.className=cls;d.textContent=text;chat.appendChild(d);while(chat.children.length>6)chat.firstChild.remove();
  }
  function voiceFor(u){
    try{const voices=speechSynthesis.getVoices();u.voice=voices.find(v=>/en-US/i.test(v.lang)&&/alex|daniel|fred|aaron|evan|tom|male/i.test(v.name))||voices.find(v=>/en-US/i.test(v.lang))||null;}catch{}
  }
  function returnToIdle(){
    speaking=false;if(speech)speech.classList.remove('show');avatarZone.classList.remove('microLean','microLean2');play(idle,.72,false,false);scheduleIdleBurst(7000);
  }
  function speak(text,done){
    speaking=true;clearTimeout(idleLoopTimer);if(speech){speech.textContent=text;speech.classList.add('show');}
    play(talking,.86,true,true);
    let finished=false;
    const finish=()=>{if(finished)return;finished=true;returnToIdle();if(done)done();};
    try{
      speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.rate=.94;u.pitch=.90;u.volume=1;voiceFor(u);u.onend=finish;u.onerror=finish;speechSynthesis.speak(u);
      later(Math.max(4500,Math.min(9000,text.length*72)),finish);
    }catch{later(5200,finish);}
  }
  function glanceThenSpeak(text){
    clearTimeout(idleLoopTimer);play(chatClip,.82,true,false);later(2300,()=>speak(text));
  }
  function scheduleIdleBurst(delay=4000){
    clearTimeout(idleLoopTimer);idleLoopTimer=setTimeout(()=>{
      if(!running||speaking)return;
      play(idle,.70+Math.random()*.08,false,false);
      avatarZone.classList.remove('microLean','microLean2');
      avatarZone.classList.add(Math.random()>.5?'microLean':'microLean2');
      const burst=5200+Math.random()*4200;
      later(burst,()=>{
        if(!running||speaking)return;
        try{idle.pause();}catch{}avatarZone.classList.remove('microLean','microLean2');
        scheduleIdleBurst(6500+Math.random()*10500);
      });
    },delay);
  }
  function runDemo(){
    if(running)return;running=true;start.remove();
    try{speechSynthesis.getVoices();}catch{}
    const gameplayStart=document.getElementById('tapBtn');if(gameplayStart)try{gameplayStart.click();}catch{}
    play(idle,.74,true,false);scheduleIdleBurst(5500);

    later(18000,()=>{addLine('@mason: what are you building?','chatLine');glanceThenSpeak("I'm watching the cottage build right now. The roof is starting to come together.");});
    later(47000,()=>{if(recentFollower)recentFollower.textContent='@mason';addLine('@mason followed','eventLine');speak('Mason, thanks for the follow. I appreciate it.');});
    later(76000,()=>{if(recentGift)recentGift.textContent='@ava · Rose';addLine('@ava sent Rose','eventLine');speak('Ava, thank you for the rose. I appreciate you.');});
    later(105000,()=>{addLine('@jay: this build is relaxing','chatLine');glanceThenSpeak("Yeah, that's why I like these long builds. You can just hang out and watch it come together.");});
    later(133000,()=>{if(drinkClip){play(drinkClip,.84,true,false);later(5000,returnToIdle);}});
  }
  btn.addEventListener('click',runDemo,{once:true});
  visible(idle);
})();
