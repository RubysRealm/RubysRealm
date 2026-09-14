'use strict';
(async()=>{
  const params=new URLSearchParams(location.search);
  if(params.get('performance')!=='human') return;

  const avatarZone=document.getElementById('avatarZone');
  if(!avatarZone) return;

  const clips=[
    'https://videos.pexels.com/video-files/7047596/7047596-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/9070180/9070180-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/7849218/7849218-uhd_4096_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/9070661/9070661-uhd_3840_2160_25fps.mp4'
  ];

  const style=document.createElement('style');
  style.textContent=`
    #avatarZone.performanceHuman .avatarVideo{display:none!important}
    #humanPerformance{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center;z-index:1;filter:saturate(.72) contrast(1.08) brightness(.74) hue-rotate(330deg)}
    #humanVignette{position:absolute;inset:0;z-index:2;pointer-events:none;background:linear-gradient(180deg,rgba(10,4,8,.08),rgba(8,2,5,.34)),radial-gradient(ellipse at center,transparent 50%,rgba(0,0,0,.38) 100%)}
    #skinFaceOccluder{position:absolute;z-index:5;width:20%;aspect-ratio:.84;left:40%;top:10%;border-radius:48% 48% 45% 45%;background:rgba(8,4,8,.94);filter:blur(.6px);transform-origin:50% 70%;pointer-events:none}
    #takaradaHead{position:absolute;z-index:6;width:24%;aspect-ratio:.88;left:38%;top:7%;overflow:hidden;border-radius:45% 45% 42% 42%;transform-origin:50% 72%;pointer-events:none;filter:drop-shadow(0 .5vh 1vh rgba(0,0,0,.5))}
    #takaradaHead img{position:absolute;width:345%;height:auto;left:-123%;top:-18%;max-width:none}
    #takaradaHead.speaking{animation:headTalk .34s ease-in-out infinite alternate}
    @keyframes headTalk{from{transform:translate(var(--tx,0px),var(--ty,0px)) rotate(var(--rot,0deg)) scale(1)}to{transform:translate(var(--tx,0px),calc(var(--ty,0px) + .18vh)) rotate(var(--rot,0deg)) scale(1.012)}}
    #humanPerformanceLabel{position:absolute;left:1.8%;bottom:1.8%;z-index:7;padding:.4vh .7vh;border-radius:999px;background:rgba(0,0,0,.45);font-size:.9vh;opacity:.0;pointer-events:none}
  `;
  document.head.appendChild(style);

  avatarZone.classList.add('performanceHuman');
  const video=document.createElement('video');
  video.id='humanPerformance'; video.muted=true; video.autoplay=true; video.playsInline=true; video.crossOrigin='anonymous';
  const vignette=document.createElement('div'); vignette.id='humanVignette';
  const occ=document.createElement('div'); occ.id='skinFaceOccluder';
  const head=document.createElement('div'); head.id='takaradaHead';
  const headImg=document.createElement('img'); headImg.src='/takarada-avatar.jpg'; head.appendChild(headImg);
  const label=document.createElement('div'); label.id='humanPerformanceLabel'; label.textContent='human motion driver';
  avatarZone.prepend(video); avatarZone.append(vignette,occ,head,label);

  let clipIndex=0;
  function nextClip(){
    video.src=clips[clipIndex%clips.length];
    clipIndex=(clipIndex+1)%clips.length;
    video.play().catch(()=>{});
  }
  video.addEventListener('ended',nextClip);
  video.addEventListener('error',()=>setTimeout(nextClip,1200));
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
    const shoulderDx=rs.x-ls.x, shoulderDy=rs.y-ls.y;
    const angle=Math.atan2(shoulderDy,shoulderDx)*180/Math.PI;
    const faceX=(nose.x-.5)*avatarZone.clientWidth;
    const faceY=(nose.y-.22)*avatarZone.clientHeight;
    const leanX=(shoulderMidX-.5)*avatarZone.clientWidth*.22;
    const leanY=(shoulderMidY-.56)*avatarZone.clientHeight*.18;
    const tx=(faceX*.45+leanX*.55),ty=(faceY*.42+leanY*.58);
    const rot=Math.max(-10,Math.min(10,angle*.55));
    head.style.setProperty('--tx',`${tx.toFixed(1)}px`); head.style.setProperty('--ty',`${ty.toFixed(1)}px`); head.style.setProperty('--rot',`${rot.toFixed(2)}deg`);
    if(!head.classList.contains('speaking')) head.style.transform=`translate(${tx}px,${ty}px) rotate(${rot}deg)`;
    occ.style.transform=`translate(${tx}px,${ty}px) rotate(${rot}deg)`;
  }

  async function tick(now){
    if(pose&&video.readyState>=2&&!video.paused&&now-lastDetect>66){
      lastDetect=now;
      try{const r=pose.detectForVideo(video,performance.now());applyPose(r.landmarks);}catch{}
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
