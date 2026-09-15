import fs from "fs";
import {spawn} from "child_process";

const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
const pick=a=>a[Math.floor(Math.random()*a.length)];
const cleanName=s=>String(s||"viewer").replace(/^@/,"").replace(/[_\.]+/g," ").replace(/[^a-zA-Z0-9 '\-]/g,"").trim().slice(0,28)||"viewer";
const clock=s=>{s=Math.max(0,Number(s)||0);const m=Math.floor(s/60),r=Math.floor(s%60);return `${m}:${String(r).padStart(2,"0")}`};

function ffmpegPixels(file){
 return new Promise((resolve,reject)=>{
  // Analyze only the gameplay band of the 9:16 render (36%-85% of frame).
  const args=["-hide_banner","-loglevel","error","-i",file,"-vf","crop=iw:ih*0.49:0:ih*0.36,scale=64:56","-frames:v","1","-f","rawvideo","-pix_fmt","rgb24","pipe:1"];
  const p=spawn("ffmpeg",args,{stdio:["ignore","pipe","pipe"]});const chunks=[];let err="";
  p.stdout.on("data",d=>chunks.push(d));p.stderr.on("data",d=>err=(err+String(d)).slice(-1000));
  p.on("error",reject);p.on("close",c=>c?reject(new Error(err||`ffmpeg ${c}`)):resolve(Buffer.concat(chunks)));
 });
}

function classify(raw,prev,title=""){
 const n=Math.floor(raw.length/3);let bright=0,green=0,blue=0,white=0,brown=0,gray=0,dark=0,sat=0;
 for(let i=0;i<n;i++){
  const r=raw[i*3],g=raw[i*3+1],b=raw[i*3+2],mx=Math.max(r,g,b),mn=Math.min(r,g,b),v=(r+g+b)/3;
  bright+=v;sat+=(mx-mn);if(v<55)dark++;if(r>180&&g>180&&b>180&&mx-mn<42)white++;
  if(g>75&&g>r*1.10&&g>b*1.06)green++;if(b>85&&b>r*1.14&&b>g*1.04)blue++;
  if(r>78&&r>g*1.06&&g>b*1.05)brown++;if(mx-mn<24&&v>55&&v<190)gray++;
 }
 let diff=0;if(prev&&prev.length===raw.length){for(let i=0;i<raw.length;i+=6)diff+=Math.abs(raw[i]-prev[i])+Math.abs(raw[i+1]-prev[i+1])+Math.abs(raw[i+2]-prev[i+2]);diff/=((raw.length/6)*3*255)}
 const f=x=>x/n,avg=bright/n,theme=String(title).toLowerCase();let scene="build";
 if(f(dark)>.42||avg<68||theme.includes("cave"))scene="dark/cave";
 else if(f(white)>.23||theme.includes("snow")||theme.includes("christmas"))scene="snow/bright";
 else if(f(blue)>.19||theme.includes("river")||theme.includes("lake")||theme.includes("beach")||theme.includes("rain"))scene="water/rain";
 else if(f(green)>.18||theme.includes("forest")||theme.includes("jungle")||theme.includes("meadow")||theme.includes("garden"))scene="forest/greenery";
 else if(f(gray)>.34)scene="stone/interior";
 else if(f(brown)>.19)scene="wood/structure";
 const motion=diff>.115?"high":diff>.05?"medium":"low";
 return {scene,motion,brightness:Math.round(avg),change:Number(diff.toFixed(3)),green:Number(f(green).toFixed(2)),blue:Number(f(blue).toFixed(2)),white:Number(f(white).toFixed(2)),brown:Number(f(brown).toFixed(2)),dark:Number(f(dark).toFixed(2)),saturation:Math.round(sat/n)};
}

function sceneWords(ctx){
 switch(ctx?.scene){
  case "dark/cave":return "the darker underground section";
  case "snow/bright":return "the snowy, brighter section";
  case "water/rain":return "the rainy or waterside section";
  case "forest/greenery":return "the greener outdoor section";
  case "stone/interior":return "the stone or interior section";
  case "wood/structure":return "the structure-heavy section";
  default:return "this part of the build";
 }
}

function gameplayLines(ctx,title){
 const where=sceneWords(ctx);const slow=ctx.motion==="low",fast=ctx.motion==="high";let a=[];
 if(ctx.scene==="dark/cave")a=["We are in the darker part right now. The lighting makes this section feel completely different.","This underground section has a really good atmosphere. I like the contrast down here."];
 else if(ctx.scene==="snow/bright")a=["We are in the snowy section now. This part looks ridiculously cozy.","The brighter snow palette changes the whole feel of this build."];
 else if(ctx.scene==="water/rain")a=["We are around the water and rain right now. This is probably the most relaxing part to watch.","The water and weather are doing a lot for this section of the build."];
 else if(ctx.scene==="forest/greenery")a=["We are back in the greener outdoor section. The environment fits this build really well.","This part has opened back up into the trees and greenery. It feels a lot less boxed in."];
 else if(ctx.scene==="stone/interior")a=["This looks like more of a stone or interior pass right now. A lot of the work here is in the smaller details.","We are in a more enclosed section now. This is where the little details start doing the heavy lifting."];
 else if(ctx.scene==="wood/structure")a=["This section is really focused on the structure right now. You can see the build starting to read more clearly.","We are on a structure-heavy part of the build now. The shape is coming together."];
 else a=["This part of the build is coming together pretty clean.","I like where this section is going. It is starting to look finished instead of just blocked out."];
 if(fast)a.push(`There is a lot more movement in ${where} right now. This is one of the more active stretches of the video.`);
 if(slow)a.push(`This is a slower detail pass through ${where}. It is more about the small changes than big movement.`);
 return a;
}

export function createDirector({framePath="/tmp/cloud-frame.jpg",getState,emitEvent}){
 let previous=null,context={scene:"waiting",motion:"low",brightness:0,change:0};let lastAnalyzed=0,lastCommentary=0,nextCommentary=Date.now()+45000,lastLine="",likesSinceThanks=0,lastLikeThanks=0,shares=0,analysisError=null;
 const history=[];
 function remember(text){history.push(text);while(history.length>12)history.shift();lastLine=text;}
 function uniquePick(lines){const options=lines.filter(x=>!history.includes(x));return pick(options.length?options:lines)}
 async function analyze(){
  if(!fs.existsSync(framePath))return context;
  try{const raw=await ffmpegPixels(framePath);const s=getState();context={...classify(raw,previous,s.current?.title),videoId:s.current?.id,title:s.current?.title,position:Number(s.cloudPlayerState?.position||0),updatedAt:Date.now()};previous=raw;lastAnalyzed=Date.now();analysisError=null;return context}catch(e){analysisError=String(e.message||e).slice(0,180);return context}
 }
 function speakGameplay(force=false){
  const s=getState();if(!s.playing||s.cloudPlayerState?.label!=="playing"||s.playbackTest&&!force)return false;
  if(!force&&Date.now()<nextCommentary)return false;
  const text=uniquePick(gameplayLines(context,s.current?.title||"the build"));remember(text);lastCommentary=Date.now();nextCommentary=Date.now()+70000+Math.floor(Math.random()*65000);
  emitEvent("commentary",text,{reason:"gameplay",context:{...context}});return true;
 }
 function reply(user,text){
  const s=getState(),name=cleanName(user),q=String(text||"").trim(),t=q.toLowerCase();if(!q)return null;let r=null;
  if(/\b(hi|hello|hey|yo)\b/.test(t))r=`Hey ${name}, welcome in.`;
  else if(/what.*(build|building|map|video)|what is this|what are (you|they) doing/.test(t))r=`This is ${s.current?.title||"the current Minecraft build"}. Right now we are in ${sceneWords(context)}.`;
  else if(/where.*(are|at)|what part|how far|timestamp|time.*video/.test(t))r=`We are about ${clock(s.cloudPlayerState?.position)} into ${s.current?.title||"this build"}, in ${sceneWords(context)}.`;
  else if(/rain|water|river|lake/.test(t)&&context.scene==="water/rain")r=`Yeah ${name}, we are right in the rainy or waterside part now. It makes this section way more relaxing.`;
  else if(/cave|dark|underground/.test(t)&&context.scene==="dark/cave")r=`Yep ${name}, this is the darker underground stretch right now.`;
  else if(/snow|winter|christmas/.test(t)&&context.scene==="snow/bright")r=`Yep ${name}, we are in the snowy section right now.`;
  else if(/love|nice|cool|great|amazing|clean|beautiful|cozy|relax/.test(t))r=`Glad you like it, ${name}. ${uniquePick(gameplayLines(context,s.current?.title||"the build")).split(".")[0]}.`;
  else if(/\?$/.test(q)||/\b(what|why|where|when|how|which|who|is|are|do|does|can)\b/.test(t))r=`I see your question, ${name}. We are at ${clock(s.cloudPlayerState?.position)} and right now it looks like ${sceneWords(context)}.`;
  else if(Math.random()<.28)r=`I see you, ${name}. Thanks for hanging out.`;
  if(r){remember(r);emitEvent("commentary",r,{reason:"chat",replyTo:user,context:{...context}})}return r;
 }
 function onLike(user,count=1){likesSinceThanks+=Math.max(1,Number(count)||1);const now=Date.now();if(likesSinceThanks>=100&&now-lastLikeThanks>60000){const n=likesSinceThanks;likesSinceThanks=0;lastLikeThanks=now;const text=n>=500?"You all are going crazy with the likes. I appreciate that.":"I see the likes coming in. Thank you, seriously.";remember(text);emitEvent("commentary",text,{reason:"likes",user,likeBurst:n});return true}return false}
 function onShare(user){shares++;if(Date.now()-lastCommentary<18000)return false;const name=cleanName(user),text=`${name}, thanks for sharing the live. I appreciate you.`;remember(text);emitEvent("commentary",text,{reason:"share",user});return true}
 async function tick(){const s=getState();if(s.cloudPlayerState?.label==="playing"&&Date.now()-lastAnalyzed>9000)await analyze();speakGameplay(false)}
 const timer=setInterval(()=>tick().catch(()=>{}),5000);timer.unref?.();
 return {reply,onLike,onShare,analyze,forceCommentary:()=>speakGameplay(true),stop:()=>clearInterval(timer),state:()=>({context,lastAnalyzed,lastCommentary,nextCommentary,lastLine,likesSinceThanks,shares,analysisError,history:[...history]})};
}
