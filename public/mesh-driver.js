'use strict';
(async()=>{
  const q=new URLSearchParams(location.search);
  if(q.get('performance')!=='mesh') return;

  const zone=document.getElementById('avatarZone');
  if(!zone) return;
  zone.classList.add('meshDriven');

  const style=document.createElement('style');
  style.textContent=`
    #avatarZone.meshDriven .avatarVideo{display:none!important}
    #takaradaMesh{position:absolute;inset:0;width:100%;height:100%;display:block;z-index:1;background:#0e0d18}
    #meshDriver{position:fixed;left:-10000px;top:-10000px;width:320px;height:180px;opacity:.001;pointer-events:none}
    #meshStart{position:absolute;inset:0;z-index:25;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.30)}
    #meshStart button{border:0;border-radius:999px;background:#ff1744;color:#fff;padding:1.3vh 2vh;font-size:1.55vh;font-weight:900;box-shadow:0 8px 28px rgba(0,0,0,.45)}
  `;
  document.head.appendChild(style);

  const canvas=document.createElement('canvas');
  canvas.id='takaradaMesh';
  zone.prepend(canvas);
  const ctx=canvas.getContext('2d',{alpha:false,desynchronized:true});

  const avatar=new Image();
  avatar.decoding='async';
  avatar.src='/takarada-avatar.jpg';
  await new Promise((resolve,reject)=>{avatar.onload=resolve;avatar.onerror=reject;});

  const driver=document.createElement('video');
  driver.id='meshDriver';
  driver.muted=true;driver.playsInline=true;driver.crossOrigin='anonymous';driver.preload='auto';
  document.body.appendChild(driver);

  const drivers=[
    'https://videos.pexels.com/video-files/7047596/7047596-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/9070180/9070180-uhd_3840_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/7849218/7849218-uhd_4096_2160_25fps.mp4',
    'https://videos.pexels.com/video-files/8128280/8128280-uhd_3840_2160_25fps.mp4'
  ];
  let driveIndex=0;
  const loadDriver=()=>{driver.src=drivers[driveIndex++%drivers.length];driver.load();driver.play().catch(()=>{});};
  driver.addEventListener('ended',loadDriver);
  driver.addEventListener('error',()=>setTimeout(loadDriver,900));
  loadDriver();

  let pose=null;
  try{
    const vision=await import('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/+esm');
    const files=await vision.FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm');
    pose=await vision.PoseLandmarker.createFromOptions(files,{
      baseOptions:{modelAssetPath:'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',delegate:'GPU'},
      runningMode:'VIDEO',numPoses:1,minPoseDetectionConfidence:.30,minPosePresenceConfidence:.30,minTrackingConfidence:.30
    });
  }catch(err){console.warn('Takarada mesh pose tracker using procedural fallback',err?.message||err);}

  const motion={
    headX:0,headY:0,headR:0,torsoX:0,torsoY:0,torsoR:0,
    leftX:0,leftY:0,rightX:0,rightY:0,energy:0
  };
  const target={...motion};
  let neutral=null,lastPoseAt=0,lastDetect=0;

  function clamp(v,a=-1,b=1){return Math.max(a,Math.min(b,v));}
  function readPose(result){
    const p=result?.landmarks?.[0];
    if(!p) return false;
    const n=p[0],ls=p[11],rs=p[12],le=p[13],re=p[14],lw=p[15],rw=p[16];
    if(!n||!ls||!rs) return false;
    const mid={x:(ls.x+rs.x)/2,y:(ls.y+rs.y)/2};
    const sample={
      nx:n.x,ny:n.y,mx:mid.x,my:mid.y,
      ang:Math.atan2(rs.y-ls.y,rs.x-ls.x),
      lx:lw?.x??le?.x??ls.x,ly:lw?.y??le?.y??ls.y,
      rx:rw?.x??re?.x??rs.x,ry:rw?.y??re?.y??rs.y,
      lsx:ls.x,lsy:ls.y,rsx:rs.x,rsy:rs.y
    };
    if(!neutral){neutral={...sample};return true;}
    target.headX=clamp((sample.nx-neutral.nx)*6.0);
    target.headY=clamp((sample.ny-neutral.ny)*6.0);
    target.headR=clamp((sample.ang-neutral.ang)*4.0);
    target.torsoX=clamp((sample.mx-neutral.mx)*5.2);
    target.torsoY=clamp((sample.my-neutral.my)*4.2);
    target.torsoR=clamp((sample.ang-neutral.ang)*2.2);
    target.leftX=clamp(((sample.lx-sample.lsx)-(neutral.lx-neutral.lsx))*5.2);
    target.leftY=clamp(((sample.ly-sample.lsy)-(neutral.ly-neutral.lsy))*4.4);
    target.rightX=clamp(((sample.rx-sample.rsx)-(neutral.rx-neutral.rsx))*5.2);
    target.rightY=clamp(((sample.ry-sample.rsy)-(neutral.ry-neutral.rsy))*4.4);
    target.energy=clamp((Math.abs(target.leftX)+Math.abs(target.leftY)+Math.abs(target.rightX)+Math.abs(target.rightY))/2.3,0,1);
    lastPoseAt=performance.now();
    return true;
  }

  function fitCanvas(){
    const dpr=Math.min(2,window.devicePixelRatio||1);
    const cssW=Math.max(2,zone.clientWidth),cssH=Math.max(2,zone.clientHeight);
    const W=Math.round(cssW*dpr),H=Math.round(cssH*dpr);
    if(canvas.width!==W||canvas.height!==H){canvas.width=W;canvas.height=H;canvas.style.width=cssW+'px';canvas.style.height=cssH+'px';}
    return {W,H,dpr};
  }
  function cover(iw,ih,W,H){const s=Math.max(W/iw,H/ih),w=iw*s,h=ih*s;return {x:(W-w)/2,y:(H-h)/2,w,h};}

  // Dense image mesh.  The whole original frame is continuously deformed; no cropped mouth,
  // swapped stills, or exposed driving footage is used.
  const COLS=22,ROWS=15;
  const src=[];
  for(let y=0;y<=ROWS;y++)for(let x=0;x<=COLS;x++)src.push({u:x/COLS,v:y/ROWS});

  function weight(px,py,cx,cy,rx,ry){
    const dx=(px-cx)/rx,dy=(py-cy)/ry,d=dx*dx+dy*dy;
    if(d>=1)return 0;
    const s=1-d;return s*s*(3-2*s);
  }
  function rotateOffset(px,py,cx,cy,ang,w){
    const x=px-cx,y=py-cy,s=Math.sin(ang*w),c=Math.cos(ang*w);
    return {x:(x*c-y*s)-x,y:(x*s+y*c)-y};
  }

  function deformed(base,t,reacting){
    const out=new Array(src.length);
    const amp=Math.min(base.w,base.h);
    const breathe=Math.sin(t*1.20)*amp*.0015;
    const talk=reacting?(0.5+0.5*Math.sin(t*17.5)) : 0;
    const blinkPhase=(t%4.7);
    const blink=blinkPhase>4.55?Math.sin((blinkPhase-4.55)/.15*Math.PI):0;

    for(let i=0;i<src.length;i++){
      const {u,v}=src[i];
      let x=base.x+u*base.w,y=base.y+v*base.h;
      let dx=0,dy=0;

      // head + neck
      let w=weight(u,v,.50,.235,.23,.25);
      dx+=w*motion.headX*amp*.010;dy+=w*motion.headY*amp*.008;
      let r=rotateOffset(x,y,base.x+.50*base.w,base.y+.29*base.h,motion.headR*.045,w);dx+=r.x;dy+=r.y;

      // shoulders/torso lean and breathing
      w=weight(u,v,.50,.52,.37,.34);
      dx+=w*motion.torsoX*amp*.0075;dy+=w*(motion.torsoY*amp*.006+breathe);
      r=rotateOffset(x,y,base.x+.50*base.w,base.y+.53*base.h,motion.torsoR*.026,w);dx+=r.x;dy+=r.y;

      // left gaming arm / hand zone
      w=weight(u,v,.30,.68,.28,.28);
      dx+=w*motion.leftX*amp*.016;dy+=w*motion.leftY*amp*.013;
      // right gaming arm / hand zone
      w=weight(u,v,.70,.68,.28,.28);
      dx+=w*motion.rightX*amp*.016;dy+=w*motion.rightY*amp*.013;

      // typing/controller micro motion, only around lower forearms/hands
      const keys=Math.sin(t*10.6)+.55*Math.sin(t*14.1+1.7);
      w=weight(u,v,.33,.78,.22,.18);dy+=w*keys*amp*.0017;
      w=weight(u,v,.67,.78,.22,.18);dy-=w*keys*amp*.00155;

      // face animation is a local mesh deformation, not a mouth cutout.
      w=weight(u,v,.50,.285,.16,.105);
      if(reacting){
        const my=(v-.285);
        dy+=w*(my>=0?1:-.18)*talk*amp*.010;
        dx+=(u-.50)*w*talk*amp*.003;
      }
      // blink compresses the eye band within the same full-frame mesh.
      w=weight(u,v,.50,.215,.17,.050);
      dy+=(v-.215)*w*(-blink*.75)*amp*.018;

      out[i]={x:x+dx,y:y+dy};
    }
    return out;
  }

  function tri(s0,s1,s2,d0,d1,d2){
    const x0=s0.u*avatar.width,y0=s0.v*avatar.height;
    const x1=s1.u*avatar.width,y1=s1.v*avatar.height;
    const x2=s2.u*avatar.width,y2=s2.v*avatar.height;
    const det=x0*(y1-y2)+x1*(y2-y0)+x2*(y0-y1);
    if(Math.abs(det)<1e-7)return;
    const a=(d0.x*(y1-y2)+d1.x*(y2-y0)+d2.x*(y0-y1))/det;
    const c=(d0.x*(x2-x1)+d1.x*(x0-x2)+d2.x*(x1-x0))/det;
    const e=(d0.x*(x1*y2-x2*y1)+d1.x*(x2*y0-x0*y2)+d2.x*(x0*y1-x1*y0))/det;
    const b=(d0.y*(y1-y2)+d1.y*(y2-y0)+d2.y*(y0-y1))/det;
    const d=(d0.y*(x2-x1)+d1.y*(x0-x2)+d2.y*(x1-x0))/det;
    const f=(d0.y*(x1*y2-x2*y1)+d1.y*(x2*y0-x0*y2)+d2.y*(x0*y1-x1*y0))/det;
    ctx.save();
    ctx.beginPath();ctx.moveTo(d0.x,d0.y);ctx.lineTo(d1.x,d1.y);ctx.lineTo(d2.x,d2.y);ctx.closePath();ctx.clip();
    ctx.setTransform(a,b,c,d,e,f);
    ctx.drawImage(avatar,0,0);
    ctx.restore();
  }

  function drawMesh(points){
    const idx=(x,y)=>y*(COLS+1)+x;
    for(let y=0;y<ROWS;y++)for(let x=0;x<COLS;x++){
      const i00=idx(x,y),i10=idx(x+1,y),i01=idx(x,y+1),i11=idx(x+1,y+1);
      tri(src[i00],src[i10],src[i11],points[i00],points[i10],points[i11]);
      tri(src[i00],src[i11],src[i01],points[i00],points[i11],points[i01]);
    }
  }

  let previous=performance.now();
  function fallback(t){
    target.headX=Math.sin(t*.43)*.28+Math.sin(t*.13)*.12;
    target.headY=Math.sin(t*.31+1)*.18;
    target.headR=Math.sin(t*.19)*.18;
    target.torsoX=Math.sin(t*.15)*.15;target.torsoY=Math.sin(t*.22)*.12;target.torsoR=Math.sin(t*.17)*.12;
    target.leftX=Math.sin(t*1.8)*.17+Math.sin(t*.41)*.12;target.leftY=Math.sin(t*2.35+1)*.15;
    target.rightX=Math.sin(t*2.05+1.4)*.19+Math.sin(t*.37)*.10;target.rightY=Math.sin(t*2.7+.4)*.14;
    target.energy=.22;
  }

  async function loop(now){
    const dt=Math.min(.05,Math.max(.001,(now-previous)/1000));previous=now;
    if(pose&&driver.readyState>=2&&!driver.paused&&now-lastDetect>65){
      lastDetect=now;
      try{readPose(pose.detectForVideo(driver,performance.now()));}catch{}
    }
    const t=now/1000;
    if(!pose||now-lastPoseAt>1800) fallback(t);
    const response=1-Math.pow(.0009,dt);
    for(const k of Object.keys(motion)) motion[k]+= (target[k]-motion[k])*response;

    const {W,H}=fitCanvas();
    const base=cover(avatar.width,avatar.height,W,H);
    ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='#0e0d18';ctx.fillRect(0,0,W,H);
    drawMesh(deformed(base,t,zone.classList.contains('reacting')));
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  if(q.get('demo')==='1'){
    const speech=document.getElementById('speech'),chat=document.getElementById('chat');
    const follower=document.getElementById('recentFollower'),gift=document.getElementById('recentGift');
    const gate=document.createElement('div');gate.id='meshStart';const btn=document.createElement('button');btn.textContent='▶ START FULL-MOTION TAKARADA';gate.appendChild(btn);zone.appendChild(gate);
    const add=(text,cls='eventLine')=>{if(!chat)return;const el=document.createElement('div');el.className=cls;el.textContent=text;chat.appendChild(el);while(chat.children.length>7)chat.firstChild.remove();};
    const speak=(text,ms)=>{if(speech){speech.textContent=text;speech.classList.add('show');}zone.classList.add('reacting');try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.rate=.97;u.pitch=.91;const vv=speechSynthesis.getVoices();u.voice=vv.find(v=>/en-US/i.test(v.lang)&&/alex|daniel|fred|aaron|male/i.test(v.name))||vv.find(v=>/en-US/i.test(v.lang))||null;speechSynthesis.speak(u);}catch{}setTimeout(()=>{speech?.classList.remove('show');zone.classList.remove('reacting');},ms||Math.max(4200,text.length*75));};
    btn.onclick=()=>{
      gate.remove();driver.play().catch(()=>{});document.getElementById('tapBtn')?.click();
      setTimeout(()=>{add('@mason: what are you building?','chatLine');speak("I'm watching the cottage build right now. The roof is starting to come together.",6500);},12000);
      setTimeout(()=>{if(follower)follower.textContent='@mason';add('@mason followed');speak('Mason, thanks for the follow. I appreciate it.',5200);},42000);
      setTimeout(()=>{if(gift)gift.textContent='@ava · Rose';add('@ava sent Rose');speak('Ava, thank you for the rose. I appreciate you.',5600);},73000);
      setTimeout(()=>{add('@jay: this build is relaxing','chatLine');speak("Yeah, that's why I like these long builds. You can just hang out and watch it come together.",7200);},104000);
    };
  }
})();
