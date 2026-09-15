'use strict';
(()=>{
  const params=new URLSearchParams(location.search);
  if(params.get('performance')!=='engine') return;
  const zone=document.getElementById('avatarZone');
  if(!zone) return;

  const style=document.createElement('style');
  style.textContent=`
    #avatarZone.engineMode .avatarVideo{display:none!important}
    #takaradaEngineCanvas{position:absolute;inset:0;width:100%;height:100%;z-index:1;display:block;background:#0e0d18}
    #avatarZone.engineMode #avatarFX,#avatarZone.engineMode #shade,#avatarZone.engineMode #brand,#avatarZone.engineMode #recentActivity,#avatarZone.engineMode #speech,#avatarZone.engineMode #chat{z-index:8}
    #engineBadge{position:absolute;left:2.8%;bottom:2.4%;z-index:9;padding:.42vh .72vh;border:1px solid rgba(255,255,255,.16);border-radius:999px;background:rgba(0,0,0,.42);font-size:.95vh;font-weight:900;letter-spacing:.05em;opacity:.72}
  `;
  document.head.appendChild(style);
  zone.classList.add('engineMode');

  const canvas=document.createElement('canvas');
  canvas.id='takaradaEngineCanvas';
  zone.prepend(canvas);
  const badge=document.createElement('div');
  badge.id='engineBadge';
  badge.textContent='TAKARADA • LIVE MOTION ENGINE';
  zone.appendChild(badge);

  const gl=canvas.getContext('webgl',{alpha:false,antialias:true,premultipliedAlpha:false});
  if(!gl){ badge.textContent='Motion engine unavailable'; return; }

  const vs=`
    precision highp float;
    attribute vec2 aPos;
    attribute vec2 aUV;
    uniform float uTime;
    uniform float uHeadX;
    uniform float uHeadY;
    uniform float uHeadR;
    uniform float uTorsoX;
    uniform float uTorsoY;
    uniform float uBreath;
    uniform float uLeftX;
    uniform float uLeftY;
    uniform float uRightX;
    uniform float uRightY;
    uniform float uJaw;
    uniform float uBlink;
    uniform float uReact;
    uniform vec2 uCrop;
    varying vec2 vUV;

    float ellipse(vec2 p, vec2 c, vec2 r){
      vec2 q=(p-c)/r;
      return smoothstep(1.0,.28,length(q));
    }
    vec2 rotAround(vec2 p, vec2 c, float a){
      float s=sin(a),co=cos(a); vec2 d=p-c;
      return c+vec2(co*d.x-s*d.y,s*d.x+co*d.y);
    }
    void main(){
      vec2 uv=aUV;
      vec2 p=aPos;
      float head=ellipse(uv,vec2(.50,.285),vec2(.205,.245));
      float torso=ellipse(uv,vec2(.50,.615),vec2(.37,.36));
      float leftArm=ellipse(uv,vec2(.285,.675),vec2(.19,.30));
      float rightArm=ellipse(uv,vec2(.715,.675),vec2(.19,.30));
      float leftHand=ellipse(uv,vec2(.345,.825),vec2(.15,.17));
      float rightHand=ellipse(uv,vec2(.665,.825),vec2(.15,.17));
      float jaw=ellipse(uv,vec2(.50,.385),vec2(.135,.105));
      float eyes=ellipse(uv,vec2(.50,.292),vec2(.15,.055));

      vec2 hp=rotAround(p,vec2(.50,.285),uHeadR*head);
      p=mix(p,hp,head);
      p+=vec2(uHeadX,uHeadY)*head;
      p+=vec2(uTorsoX,uTorsoY+uBreath)*torso*(1.0-head*.72);

      p+=vec2(uLeftX,uLeftY)*max(leftArm*.55,leftHand);
      p+=vec2(uRightX,uRightY)*max(rightArm*.55,rightHand);

      // speaking is a lower-face deformation, not a pasted/cropped mouth layer
      p.y += uJaw*jaw*(.016 + .010*(uv.y-.34));
      // blink compresses the actual eye region of the full texture
      p.y += uBlink*eyes*(uv.y<.292?.010:-.010);

      // reaction gesture: shoulders rise and hands briefly come alive
      p.y -= uReact*torso*.0035;
      p.x += uReact*(leftArm-rightArm)*.0025;

      vec2 clip=vec2(p.x*2.0-1.0,1.0-p.y*2.0);
      gl_Position=vec4(clip,0.0,1.0);
      vUV=vec2(uv.x,mix(uCrop.x,uCrop.y,uv.y));
    }
  `;
  const fs=`
    precision mediump float;
    uniform sampler2D uTex;
    uniform float uReact;
    varying vec2 vUV;
    void main(){
      vec4 c=texture2D(uTex,vUV);
      float vignette=1.0-.10*length((vUV-.5)*vec2(1.15,.92));
      c.rgb*=vignette;
      c.rgb+=uReact*vec3(.008,.001,.002);
      gl_FragColor=vec4(c.rgb,1.0);
    }
  `;
  function shader(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(s));return s;}
  const program=gl.createProgram();
  try{gl.attachShader(program,shader(gl.VERTEX_SHADER,vs));gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fs));gl.linkProgram(program);if(!gl.getProgramParameter(program,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(program));}
  catch(e){console.error(e);badge.textContent='Motion engine shader failed';return;}
  gl.useProgram(program);

  const cols=40,rows=32,verts=[],uvs=[],idx=[];
  for(let y=0;y<=rows;y++)for(let x=0;x<=cols;x++){const u=x/cols,v=y/rows;verts.push(u,v);uvs.push(u,v);}
  for(let y=0;y<rows;y++)for(let x=0;x<cols;x++){
    const a=y*(cols+1)+x,b=a+1,c=a+cols+1,d=c+1;
    idx.push(a,c,b,b,c,d);
  }
  function buf(data,type=gl.ARRAY_BUFFER){const b=gl.createBuffer();gl.bindBuffer(type,b);gl.bufferData(type,data,gl.STATIC_DRAW);return b;}
  const pbuf=buf(new Float32Array(verts)),ubuf=buf(new Float32Array(uvs)),ibuf=buf(new Uint16Array(idx),gl.ELEMENT_ARRAY_BUFFER);
  function attr(name,b){const l=gl.getAttribLocation(program,name);gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.enableVertexAttribArray(l);gl.vertexAttribPointer(l,2,gl.FLOAT,false,0,0);}
  attr('aPos',pbuf);attr('aUV',ubuf);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ibuf);

  const U={};['uTime','uHeadX','uHeadY','uHeadR','uTorsoX','uTorsoY','uBreath','uLeftX','uLeftY','uRightX','uRightY','uJaw','uBlink','uReact','uCrop','uTex'].forEach(n=>U[n]=gl.getUniformLocation(program,n));
  const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
  gl.uniform1i(U.uTex,0);

  const img=new Image();img.crossOrigin='anonymous';img.src='/takarada-avatar.jpg';
  let ready=false,crop=[0,1];
  function resize(){
    const dpr=Math.min(2,window.devicePixelRatio||1),w=Math.max(2,Math.floor(zone.clientWidth*dpr)),h=Math.max(2,Math.floor(zone.clientHeight*dpr));
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;gl.viewport(0,0,w,h);}
    if(img.naturalWidth){const ir=img.naturalWidth/img.naturalHeight,cr=w/h;if(cr>ir){const span=ir/cr;crop=[(1-span)/2,(1+span)/2];}else crop=[0,1];}
  }
  img.onload=()=>{gl.bindTexture(gl.TEXTURE_2D,tex);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,img);ready=true;resize();};
  window.addEventListener('resize',resize);resize();

  let react=0,reactTarget=0,jaw=0,blink=0,nextBlink=performance.now()+1800+Math.random()*2600;
  let gestureKick=0,chatKick=0,lastSpeech='';
  const speech=document.getElementById('speech');
  const follower=document.getElementById('recentFollower');
  const gift=document.getElementById('recentGift');
  let lastFollower=follower?.textContent||'',lastGift=gift?.textContent||'';

  const obs=new MutationObserver(()=>{
    const active=zone.classList.contains('reacting');
    reactTarget=active?1:0;
    const text=(speech?.textContent||'').trim();
    if(text&&text!==lastSpeech){lastSpeech=text;gestureKick=1;}
  });
  obs.observe(zone,{attributes:true,attributeFilter:['class'],subtree:false});
  if(speech)obs.observe(speech,{childList:true,characterData:true,subtree:true});
  if(follower)new MutationObserver(()=>{const v=follower.textContent;if(v!==lastFollower){lastFollower=v;gestureKick=1.25;}}).observe(follower,{childList:true,subtree:true,characterData:true});
  if(gift)new MutationObserver(()=>{const v=gift.textContent;if(v!==lastGift){lastGift=v;gestureKick=1.55;}}).observe(gift,{childList:true,subtree:true,characterData:true});

  function n1(t,a,b,c){return Math.sin(t*a)+.52*Math.sin(t*b+1.7)+.31*Math.sin(t*c+4.1);}
  function frame(ms){
    requestAnimationFrame(frame);if(!ready)return;resize();
    const t=ms*.001;
    react+=(reactTarget-react)*.075;gestureKick*=.967;chatKick*=.96;
    if(ms>nextBlink){blink=1;nextBlink=ms+2200+Math.random()*4300;}blink*=.82;

    const gaming=n1(t,.43,.77,1.21);
    const focus=n1(t,.18,.31,.53);
    const talk=react>.08 ? Math.max(0,.42+.33*Math.sin(t*12.7)+.22*Math.sin(t*19.4+1.2)+.12*Math.sin(t*27.1)) : 0;
    jaw+=(talk-jaw)*.32;

    const headX=.0028*n1(t,.21,.47,.93)+gestureKick*.0018*Math.sin(t*6.0);
    const headY=.0018*n1(t,.17,.39,.72)-react*.0015+gestureKick*.0012*Math.sin(t*5.3+1.1);
    const headR=.0085*n1(t,.12,.29,.61)+react*.006*Math.sin(t*2.5)+gestureKick*.008*Math.sin(t*4.1);
    const torsoX=.0015*n1(t,.09,.22,.36);
    const torsoY=.0012*n1(t,.11,.19,.33);
    const breath=.0012+.0011*Math.sin(t*1.45);

    // two different continuous gaming motions: keyboard hand and mouse hand
    const leftX=.0038*(.45*Math.sin(t*5.1)+.28*Math.sin(t*7.8+1.4))+react*.002*Math.sin(t*3.0)+gestureKick*.004*Math.sin(t*4.6);
    const leftY=.0026*(.55*Math.sin(t*4.4+2.0)+.24*Math.sin(t*9.1))+gestureKick*.003*Math.abs(Math.sin(t*4.6));
    const rightX=.0046*(.62*Math.sin(t*1.9)+.21*Math.sin(t*6.3+2.2))+react*.0018*Math.sin(t*3.5+1.0)+gestureKick*.0045*Math.sin(t*4.2+1.2);
    const rightY=.0028*(.48*Math.sin(t*2.2+1.7)+.18*Math.sin(t*5.6))+gestureKick*.0026*Math.abs(Math.sin(t*4.2+1.2));

    gl.useProgram(program);gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,tex);
    gl.uniform1f(U.uTime,t);gl.uniform1f(U.uHeadX,headX);gl.uniform1f(U.uHeadY,headY);gl.uniform1f(U.uHeadR,headR);
    gl.uniform1f(U.uTorsoX,torsoX);gl.uniform1f(U.uTorsoY,torsoY);gl.uniform1f(U.uBreath,breath);
    gl.uniform1f(U.uLeftX,leftX);gl.uniform1f(U.uLeftY,leftY);gl.uniform1f(U.uRightX,rightX);gl.uniform1f(U.uRightY,rightY);
    gl.uniform1f(U.uJaw,jaw);gl.uniform1f(U.uBlink,blink);gl.uniform1f(U.uReact,Math.min(1.4,react+gestureKick*.55));gl.uniform2f(U.uCrop,crop[0],crop[1]);
    gl.drawElements(gl.TRIANGLES,idx.length,gl.UNSIGNED_SHORT,0);
  }
  requestAnimationFrame(frame);

  // Optional self-test so the user can see speech/event motion without a live TikTok room.
  if(params.get('demo')==='1'){
    const start=document.createElement('button');
    start.textContent='▶ START ENGINE TEST';
    Object.assign(start.style,{position:'absolute',zIndex:'30',left:'50%',top:'50%',transform:'translate(-50%,-50%)',border:'0',borderRadius:'999px',padding:'1.2vh 1.8vh',background:'#ff1744',color:'#fff',fontSize:'1.45vh',fontWeight:'900'});
    zone.appendChild(start);
    start.onclick=()=>{
      start.remove();
      const fire=(text,ms=4600)=>{if(speech){speech.textContent=text;speech.classList.add('show');}zone.classList.add('reacting');setTimeout(()=>{zone.classList.remove('reacting');speech?.classList.remove('show');},ms);};
      setTimeout(()=>fire('Thanks for the follow, Mason.'),7000);
      setTimeout(()=>fire('Ava, thank you for the rose. I appreciate you.'),26000);
      setTimeout(()=>fire('Yeah, this cottage build is coming together really clean.'),48000);
    };
  }
})();
