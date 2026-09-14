'use strict';
(async()=>{
  const params=new URLSearchParams(location.search);
  if(params.get('performance')!=='rig') return;
  const demo=params.get('demo')==='1';
  const avatarZone=document.getElementById('avatarZone');
  if(!avatarZone) return;

  const style=document.createElement('style');
  style.textContent=`
    #avatarZone.performanceRig .avatarVideo{display:none!important}
    #takaradaRig{position:absolute;inset:0;width:100%;height:100%;z-index:1;display:block;background:#0e0d18}
    #rigDriver{position:fixed!important;left:-10000px!important;top:-10000px!important;width:320px!important;height:180px!important;opacity:.001!important;pointer-events:none!important}
    #rigStart{position:absolute;inset:0;z-index:20;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.28)}
    #rigStart button{border:0;border-radius:999px;background:#ff1744;color:white;padding:1.25vh 1.8vh;font-size:1.55vh;font-weight:900;box-shadow:0 8px 28px rgba(0,0,0,.45)}
  `;
  document.head.appendChild(style);
  avatarZone.classList.add('performanceRig');

  const canvas=document.createElement('canvas');
  canvas.id='takaradaRig';
  const ctx=canvas.getContext('2d',{alpha:false});
  avatarZone.prepend(canvas);

  const avatar=new Image();
  avatar.src='/takarada-avatar.jpg';
  await new Promise((resolve,reject)=>{avatar.onload=resolve;avatar.onerror=reject;});

  const driver=document.createElement('video');
  driver.id='rigDriver';driver.muted=true;driver.playsInline=true;driver.crossOrigin='anonymous';driver.preload='auto';
  document.body.appendChild(driver);
  const clips=[
    'https://videos.pexels.com/video-files/8128280/8128280-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/7047596/7047596-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/9070180/9070180-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/7849218/7849218-uhd_4096_2160_25fps.mp4'
  ];
  let clipIndex=0;
  function nextClip(){driver.src=clips[clipIndex++%clips.length];driver.play().catch(()=>{});}
  driver.addEventListener('ended',nextClip);driver.addEventListener('error',()=>setTimeout(nextClip,1000));nextClip();

  let pose=null,lastDetect=0,poseTarget={hx:0,hy:0,rot:0,lx:0,ly:0,rx:0,ry:0};
  try{
    const vision=await import('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/+esm');
    const fileset=await vision.FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm');
    pose=await vision.PoseLandmarker.createFromOptions(fileset,{baseOptions:{modelAssetPath:'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',delegate:'GPU'},runningMode:'VIDEO',numPoses:1,minPoseDetectionConfidence:.3,minTrackingConfidence:.3});
  }catch(e){console.warn('rig pose fallback',e?.message||e);}

  function readPose(lm){
    if(!lm||!lm[0]) return;
    const p=lm[0],nose=p[0],ls=p[11],rs=p[12],lw=p[15],rw=p[16];
    if(!nose||!ls||!rs) return;
    const midX=(ls.x+rs.x)/2,midY=(ls.y+rs.y)/2;
    poseTarget.hx=Math.max(-1,Math.min(1,(nose.x-midX)*7));
    poseTarget.hy=Math.max(-1,Math.min(1,(nose.y-(midY-.22))*6));
    poseTarget.rot=Math.max(-1,Math.min(1,Math.atan2(rs.y-ls.y,rs.x-ls.x)*3.5));
    if(lw){poseTarget.lx=Math.max(-1,Math.min(1,(lw.x-ls.x)*3));poseTarget.ly=Math.max(-1,Math.min(1,(lw.y-ls.y)*2.5));}
    if(rw){poseTarget.rx=Math.max(-1,Math.min(1,(rw.x-rs.x)*3));poseTarget.ry=Math.max(-1,Math.min(1,(rw.y-rs.y)*2.5));}
  }

  let sm={hx:0,hy:0,rot:0,lx:0,ly:0,rx:0,ry:0};
  const lerp=(a,b,t)=>a+(b-a)*t;
  function fit(){const dpr=Math.min(2,window.devicePixelRatio||1),w=avatarZone.clientWidth,h=avatarZone.clientHeight;if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);canvas.style.width=w+'px';canvas.style.height=h+'px';ctx.setTransform(dpr,0,0,dpr,0,0);}return {w,h};}
  function coverRect(iw,ih,w,h){const s=Math.max(w/iw,h/ih);const dw=iw*s,dh=ih*s;return {x:(w-dw)/2,y:(h-dh)/2,w:dw,h:dh};}
  function drawRegion(base,norm,dx,dy,rot,scale=1){const sx=norm.x*avatar.width,sy=norm.y*avatar.height,sw=norm.w*avatar.width,sh=norm.h*avatar.height;const dx0=base.x+norm.x*base.w,dy0=base.y+norm.y*base.h,dw=norm.w*base.w,dh=norm.h*base.h;ctx.save();ctx.translate(dx0+dw/2+dx,dy0+dh/2+dy);ctx.rotate(rot);ctx.scale(scale,scale);ctx.drawImage(avatar,sx,sy,sw,sh,-dw/2,-dh/2,dw,dh);ctx.restore();}

  const HEAD={x:.355,y:.035,w:.29,h:.39};
  const TORSO={x:.24,y:.31,w:.52,h:.57};
  const LEFT={x:.05,y:.43,w:.47,h:.54};
  const RIGHT={x:.48,y:.43,w:.47,h:.54};
  const MOUTH={x:.455,y:.225,w:.09,h:.055};
  let last=performance.now();
  async function frame(now){
    const {w,h}=fit();const dt=Math.min(.05,(now-last)/1000);last=now;
    if(pose&&driver.readyState>=2&&!driver.paused&&now-lastDetect>70){lastDetect=now;try{readPose(pose.detectForVideo(driver,performance.now()).landmarks);}catch{}}
    const t=now/1000;
    if(!pose){poseTarget.hx=Math.sin(t*.47)*.35+Math.sin(t*.13)*.2;poseTarget.hy=Math.sin(t*.31)*.22;poseTarget.rot=Math.sin(t*.19)*.16;poseTarget.lx=Math.sin(t*2.3)*.15;poseTarget.ly=Math.sin(t*1.7)*.12;poseTarget.rx=Math.sin(t*2.05+1.2)*.18;poseTarget.ry=Math.sin(t*1.55+2)*.13;}
    for(const k in sm)sm[k]=lerp(sm[k],poseTarget[k],1-Math.pow(.001,dt));
    const base=coverRect(avatar.width,avatar.height,w,h);
    ctx.clearRect(0,0,w,h);
    const breathe=1+Math.sin(t*1.12)*.0017;
    ctx.save();ctx.translate(w/2,h/2);ctx.scale(breathe,breathe);ctx.drawImage(avatar,base.x-w/2,base.y-h/2,base.w,base.h);ctx.restore();
    drawRegion(base,TORSO,sm.hx*1.1,sm.hy*.8,sm.rot*.006,1+Math.sin(t*1.1)*.0018);
    drawRegion(base,LEFT,sm.lx*4.2,sm.ly*3.2,sm.rot*.003+Math.sin(t*2.05)*.0025,1);
    drawRegion(base,RIGHT,sm.rx*4.6,sm.ry*3.4,sm.rot*.003+Math.sin(t*2.2+1)*.0028,1);
    drawRegion(base,HEAD,sm.hx*5.2,sm.hy*3.8,sm.rot*.024,1+Math.sin(t*.72)*.0015);

    if(avatarZone.classList.contains('reacting')){
      const talk=(Math.sin(t*18)+1)/2,norm=MOUTH;
      const sx=norm.x*avatar.width,sy=norm.y*avatar.height,sw=norm.w*avatar.width,sh=norm.h*avatar.height;
      const dx=base.x+norm.x*base.w+sm.hx*5.2,dy=base.y+norm.y*base.h+sm.hy*3.8,dw=norm.w*base.w,dh=norm.h*base.h;
      ctx.save();ctx.translate(dx+dw/2,dy+dh/2);ctx.rotate(sm.rot*.024);ctx.scale(1,1+talk*.16);ctx.drawImage(avatar,sx,sy,sw,sh,-dw/2,-dh/2,dw,dh);ctx.restore();
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  if(demo){
    const speech=document.getElementById('speech'),chat=document.getElementById('chat'),recentFollower=document.getElementById('recentFollower'),recentGift=document.getElementById('recentGift');
    const gate=document.createElement('div');gate.id='rigStart';const btn=document.createElement('button');btn.textContent='▶ START TAKARADA WEBCAM ENGINE';gate.appendChild(btn);avatarZone.appendChild(gate);
    const add=(text,cls='eventLine')=>{const d=document.createElement('div');d.className=cls;d.textContent=text;chat?.appendChild(d);while(chat&&chat.children.length>7)chat.firstChild.remove();};
    const talk=(text,ms=4800)=>{if(speech){speech.textContent=text;speech.classList.add('show');}avatarZone.classList.add('reacting');try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.rate=.96;u.pitch=.92;const vv=speechSynthesis.getVoices();u.voice=vv.find(v=>/en-US/i.test(v.lang)&&/alex|daniel|fred|male/i.test(v.name))||vv.find(v=>/en-US/i.test(v.lang))||null;speechSynthesis.speak(u);}catch{}setTimeout(()=>{speech?.classList.remove('show');avatarZone.classList.remove('reacting');},ms);};
    btn.onclick=()=>{gate.remove();driver.play().catch(()=>{});document.getElementById('tapBtn')?.click();setTimeout(()=>{add('@viewer: what are you building?','chatLine');talk('I am watching the build with you. This one is coming together pretty clean.');},10000);setTimeout(()=>{if(recentFollower)recentFollower.textContent='@newviewer';add('@newviewer followed');talk('Thanks for the follow, new viewer.');},38000);setTimeout(()=>{if(recentGift)recentGift.textContent='@builder · Rose';add('@builder sent Rose');talk('Thank you for the rose, builder.');},68000);setTimeout(()=>{add('@viewer: this is relaxing','chatLine');talk('Yeah, this is actually a really relaxing build to watch.');},98000);};
  }
})();
