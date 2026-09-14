'use strict';
(async()=>{
  const params=new URLSearchParams(location.search);
  if(params.get('performance')!=='human') return;
  const demo=params.get('demo')==='1';
  const avatarZone=document.getElementById('avatarZone');
  if(!avatarZone) return;

  const clips=[
    'https://videos.pexels.com/video-files/8128280/8128280-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/7047596/7047596-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/9070180/9070180-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/7849218/7849218-uhd_4096_2160_25fps.mp4'
  ];

  const style=document.createElement('style');
  style.textContent=`
    #avatarZone.performanceHuman .avatarVideo{display:none!important}
    #humanPerformance{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center;z-index:1;filter:saturate(.78) contrast(1.06) brightness(.78) hue-rotate(334deg)}
    #humanVignette{position:absolute;inset:0;z-index:2;pointer-events:none;background:linear-gradient(180deg,rgba(10,4,8,.05),rgba(8,2,5,.28)),radial-gradient(ellipse at center,transparent 54%,rgba(0,0,0,.34) 100%)}
    #skinFaceOccluder{position:absolute;z-index:5;width:20%;aspect-ratio:.84;left:40%;top:10%;border-radius:48% 48% 45% 45%;background:rgba(8,4,8,.9);filter:blur(.7px);transform-origin:50% 70%;pointer-events:none}
    #takaradaHead{position:absolute;z-index:6;width:24%;aspect-ratio:.88;left:38%;top:7%;overflow:hidden;border-radius:45% 45% 42% 42%;transform-origin:50% 72%;pointer-events:none;filter:drop-shadow(0 .5vh 1vh rgba(0,0,0,.48))}
    #takaradaHead img{position:absolute;width:345%;height:auto;left:-123%;top:-18%;max-width:none}
    #takaradaHead.speaking{animation:headTalk .42s ease-in-out infinite alternate}
    @keyframes headTalk{from{transform:translate(var(--tx,0px),var(--ty,0px)) rotate(var(--rot,0deg)) scale(1)}to{transform:translate(var(--tx,0px),calc(var(--ty,0px) + .12vh)) rotate(var(--rot,0deg)) scale(1.006)}}
    #humanStart{position:absolute;inset:0;z-index:20;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.38)}
    #humanStart button{border:0;border-radius:999px;background:#ff1744;color:white;padding:1.25vh 1.8vh;font-size:1.55vh;font-weight:900;box-shadow:0 8px 28px rgba(0,0,0,.45)}
  `;
  document.head.appendChild(style);

  avatarZone.classList.add('performanceHuman');
  const video=document.createElement('video');
  video.id='humanPerformance'; video.muted=true; video.autoplay=!demo; video.playsInline=true; video.crossOrigin='anonymous'; video.preload='auto';
  const vignette=document.createElement('div'); vignette.id='humanVignette';
  const occ=document.createElement('div'); occ.id='skinFaceOccluder';
  const head=document.createElement('div'); head.id='takaradaHead';
  const headImg=document.createElement('img'); headImg.src='/takarada-avatar.jpg'; head.appendChild(headImg);
  avatarZone.prepend(video); avatarZone.append(vignette,occ,head);

  let clipIndex=0;
  function nextClip(){
    video.src=clips[clipIndex%clips.length];
    clipIndex=(clipIndex+1)%clips.length;
    if(!demo) video.play().catch(()=>{});
  }
  video.addEventListener('ended',nextClip);
  video.addEventListener('error',()=>setTimeout(nextClip,900));
  nextClip();

  const speechObserver=new MutationObserver(()=>head.classList.toggle('speaking',avatarZone.classList.contains('reacting')));
  speechObserver.observe(avatarZone,{attributes:true,attributeFilter:['class']});

  let pose=null,lastDetect=0;
  try{
    const vision=await import('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/+esm');
    const fileset=await vision.FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm');
    pose=await vision.PoseLandmarker.createFromOptions(fileset,{
      baseOptions:{modelAssetPath:'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',delegate:'GPU'},
      runningMode:'VIDEO',numPoses:1,minPoseDetectionConfidence:.35,minTrackingConfidence:.35
    });
  }catch(e){console.warn('Human performance pose tracker fallback',e?.message||e);}

  function applyPose(lm){
    if(!lm||!lm[0]) return;
    const p=lm[0],nose=p[0],ls=p[11],rs=p[12];
    if(!nose||!ls||!rs) return;
    const shoulderMidX=(ls.x+rs.x)/2, shoulderMidY=(ls.y+rs.y)/2;
    const angle=Math.atan2(rs.y-ls.y,rs.x-ls.x)*180/Math.PI;
    const faceX=(nose.x-.5)*avatarZone.clientWidth;
    const faceY=(nose.y-.22)*avatarZone.clientHeight;
    const leanX=(shoulderMidX-.5)*avatarZone.clientWidth*.20;
    const leanY=(shoulderMidY-.56)*avatarZone.clientHeight*.16;
    const tx=faceX*.46+leanX*.54,ty=faceY*.44+leanY*.56;
    const rot=Math.max(-9,Math.min(9,angle*.5));
    head.style.setProperty('--tx',`${tx.toFixed(1)}px`);head.style.setProperty('--ty',`${ty.toFixed(1)}px`);head.style.setProperty('--rot',`${rot.toFixed(2)}deg`);
    if(!head.classList.contains('speaking'))head.style.transform=`translate(${tx}px,${ty}px) rotate(${rot}deg)`;
    occ.style.transform=`translate(${tx}px,${ty}px) rotate(${rot}deg)`;
  }

  async function tick(now){
    if(pose&&video.readyState>=2&&!video.paused&&now-lastDetect>75){
      lastDetect=now;
      try{const r=pose.detectForVideo(video,performance.now());applyPose(r.landmarks);}catch{}
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  if(demo){
    const speech=document.getElementById('speech'),chat=document.getElementById('chat');
    const recentFollower=document.getElementById('recentFollower'),recentGift=document.getElementById('recentGift');
    const start=document.createElement('div');start.id='humanStart';
    const btn=document.createElement('button');btn.textContent='▶ START REAL-MOTION TEST';start.appendChild(btn);avatarZone.appendChild(start);
    const add=(text,cls='eventLine')=>{if(!chat)return;const d=document.createElement('div');d.className=cls;d.textContent=text;chat.appendChild(d);while(chat.children.length>7)chat.firstChild.remove();};
    const talk=(text,ms=4500)=>{
      if(speech){speech.textContent=text;speech.classList.add('show');}
      avatarZone.classList.add('reacting');
      try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.rate=.96;u.pitch=.92;const voices=speechSynthesis.getVoices();u.voice=voices.find(v=>/en-US/i.test(v.lang)&&/male|alex|daniel|fred/i.test(v.name))||voices.find(v=>/en-US/i.test(v.lang))||null;speechSynthesis.speak(u);}catch{}
      setTimeout(()=>{if(speech)speech.classList.remove('show');avatarZone.classList.remove('reacting');},ms);
    };
    btn.onclick=()=>{
      start.remove();video.play().catch(()=>{});
      setTimeout(()=>{if(recentFollower)recentFollower.textContent='@test_viewer';add('@test_viewer followed');talk('Thanks for the follow, test viewer.');},9000);
      setTimeout(()=>{if(recentGift)recentGift.textContent='@test_viewer · Rose';add('@test_viewer sent Rose');talk('Thank you for the rose, test viewer.');},32000);
      setTimeout(()=>{add('@test_viewer: what are you building?','chatLine');talk('I am watching this build with you. It is coming together pretty clean.');},61000);
      setTimeout(()=>{add('@test_viewer: this is relaxing','chatLine');talk('Yeah, this one is actually really relaxing to watch.');},94000);
    };
  }
})();
