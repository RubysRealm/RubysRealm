import express from "express";
import http from "http";
import { Server as SocketIOServer } from "socket.io";
import { spawn } from "child_process";
import fs from "fs";

const app=express();
const server=http.createServer(app);
const io=new SocketIOServer(server,{cors:{origin:"*"}});
const PORT=Number(process.env.PORT||10000);
const CONTROL_TOKEN=process.env.CONTROL_TOKEN||"change-me";
const RTMP_SERVER=(process.env.RTMP_SERVER||"").trim();
const RTMP_STREAM_KEY=(process.env.RTMP_STREAM_KEY||"").trim();
const mediaSources=JSON.parse(process.env.MEDIA_SOURCES||"{}");
const videos=[["c6FAO3-zvhE","Lush Caves"],["AirXwBsNPDw","Rainy Riverside"],["wcIUiy_Ofcw","Ghibli Nostalgic"],["y8yMP36qHXA","Rainy Swamp"],["Zoq4ogt2wtU","Pine Forest House"],["Dy3VtjcHdCs","Rainy Cliff"],["ykHsq6yUNGg","Rainy Flower Forest"],["nUbDQ0wUESU","Medieval Farmhouse"],["snvLyjMcgh0","Rainy River"],["N6S53tOB1ss","Rainy Jungle Tree House"],["C_WaC-JmhFo","Rainy Mountain"],["eHSxedwXaM0","Rainy Cherry Grove"],["oCIpgdb2pM4","Rainy Mangrove Swamp"],["yTTutYKV1rk","Rainy Overgrown Laputa Part 1"],["2byiUUc0SnQ","Rainy Overgrown Laputa Part 2"],["UDRhiTUMVQY","Ghibli Nostalgic 1.20"],["wV9VatPiPf4","Rainy Spruce Island"],["LoeTtwvBD_k","Rainy Beach House"],["-DRRSTrLHTI","Rainy Greenhouse"],["bp-1X7sQ_2M","Rainy Cherry Lake"],["Ps0oA1nt3mw","Rainy Meadow"],["pW0iacBW1MU","Snowy Mountain"],["Az9X6YFzcBU","Christmas Snow Village"],["i9U-rUObowg","Rainy Mountain 1.21"],["IsXCRoImZ3c","Rainy Pale Garden"],["AepZzZS6j_U","Rainy Dark Forest"],["GFmBMg7-b44","Rainy Farmhouse"],["CIHsdaqCXwM","Rainy River Island"],["hYJY95sAeFc","Rainy Pale Cherry"],["O6yrzYkn2i8","Rainy Old Treehouse"]].map(([id,title])=>({id,title}));
let index=0,playing=true,ffmpeg=null;
let cloudPlayerState={code:-999,label:"waiting",videoId:null,position:0,updatedAt:0};
let broadcastWanted=false,broadcastStatus="stopped",broadcastError=null,broadcastStartedAt=null;

app.use(express.json());
app.use(express.static("public"));
function auth(req,res,next){const t=req.query.token||req.headers["x-control-token"];if(t!==CONTROL_TOKEN)return res.status(403).send("Bad control token");next();}
function getRtmp(){const direct=(process.env.RTMP_URL||"").trim();if(direct)return direct;if(!RTMP_SERVER||!RTMP_STREAM_KEY)return"";return RTMP_SERVER.replace(/\/$/,"")+"/"+RTMP_STREAM_KEY.replace(/^\//,"");}
function cur(){const v=videos[index];return {...v,sourceUrl:mediaSources[v.id]||null};}
function state(){const current=cur();return{version:"gameplay-only-1",gameplayOnly:true,index,count:videos.length,playing,current,next:videos[(index+1)%videos.length],cloudPlayerState,broadcasting:!!ffmpeg,broadcastWanted,broadcastStatus,broadcastError,broadcastStartedAt,rtmpConfigured:!!getRtmp(),mediaReady:!!current.sourceUrl||cloudPlayerState.label==="playing",playbackTest:false,audioMode:"original-gameplay"};}
function nextVideo(d=1){index=(index+d+videos.length)%videos.length;playing=true;cloudPlayerState={code:-999,label:"loading",videoId:cur().id,position:0,updatedAt:Date.now()};io.emit("queue",state());}
function safeBroadcastError(value,rtmp){return String(value||"").replaceAll(rtmp,"[TikTok destination]").replace(/rtmps?:\/\/\S+/gi,"[TikTok destination]").slice(-600);}
function scheduleBroadcastRetry(){if(!broadcastWanted)return;setTimeout(()=>{if(broadcastWanted&&!ffmpeg)startBroadcast(true);},12000).unref();}
function startBroadcast(retry=false){
 if(ffmpeg)return{ok:true,message:"Broadcast already running"};
 if(cloudPlayerState.label!=="playing"||Date.now()-cloudPlayerState.updatedAt>15000){if(!retry)broadcastWanted=false;return{ok:false,message:"Gameplay is not playing in the cloud yet."};}
 const rtmp=getRtmp();if(!rtmp){if(!retry)broadcastWanted=false;return{ok:false,message:"TikTok streaming destination is not configured yet."};}
 broadcastWanted=true;broadcastStatus="starting";broadcastError=null;
 const w=process.env.STREAM_WIDTH||"720",h=process.env.STREAM_HEIGHT||"1280",fps=process.env.STREAM_FPS||"30";
 const args=["-hide_banner","-loglevel","warning","-thread_queue_size","1024","-f","x11grab","-draw_mouse","0","-framerate",fps,"-video_size",`${w}x${h}`,"-i",":99.0","-thread_queue_size","1024","-f","pulse","-i","takarada.monitor","-c:v","libx264","-preset","veryfast","-tune","zerolatency","-pix_fmt","yuv420p","-b:v","3500k","-maxrate","4000k","-bufsize","7000k","-g",String(Number(fps)*2),"-c:a","aac","-b:a","160k","-ar","44100","-f","flv",rtmp];
 ffmpeg=spawn("ffmpeg",args,{stdio:["ignore","ignore","pipe"]});let stderr="";
 ffmpeg.stderr.on("data",d=>{stderr=(stderr+String(d)).slice(-4000);});
 ffmpeg.on("spawn",()=>{broadcastStatus="streaming";broadcastStartedAt=Date.now();io.emit("status",state());});
 ffmpeg.on("error",e=>{broadcastError=safeBroadcastError(e.message,rtmp);});
 ffmpeg.on("exit",c=>{const wanted=broadcastWanted;ffmpeg=null;broadcastStartedAt=null;broadcastStatus=wanted?"reconnecting":"stopped";if(c&&!broadcastError)broadcastError=safeBroadcastError(stderr||`Encoder exited with code ${c}`,rtmp);io.emit("status",state());if(wanted)scheduleBroadcastRetry();});
 io.emit("status",state());return{ok:true,message:"Cloud encoder is connecting to TikTok with gameplay audio."};
}
function stopBroadcast(){broadcastWanted=false;broadcastStatus="stopped";broadcastError=null;broadcastStartedAt=null;if(!ffmpeg){io.emit("status",state());return{ok:true,message:"Broadcast already stopped"};}const p=ffmpeg;ffmpeg=null;p.kill("SIGTERM");io.emit("status",state());return{ok:true,message:"Cloud broadcast stopped"};}

app.get("/",(req,res)=>res.type("html").send('<meta name="viewport" content="width=device-width,initial-scale=1"><title>Takarada Gameplay Live</title><body style="background:#090a0f;color:white;font:18px system-ui;padding:32px"><h1>Takarada Gameplay Live</h1><p>Gameplay-only cloud stream.</p><a style="color:#ff5677" href="/preview">Open gameplay preview</a></body>'));
app.get("/stage",(req,res)=>res.sendFile(process.cwd()+"/public/stage.html"));
app.get("/preview",(req,res)=>res.sendFile(process.cwd()+"/public/stage.html"));
app.get("/control",auth,(req,res)=>res.sendFile(process.cwd()+"/public/control.html"));
app.get("/api/state",(req,res)=>res.json(state()));
app.post("/api/player-state",auth,(req,res)=>{if(req.body?.renderer==="cloud"){cloudPlayerState={code:Number(req.body.code),label:String(req.body.label||"unknown"),error:req.body.error||null,position:Number(req.body.position||0),duration:Number(req.body.duration||0),volume:Number(req.body.volume??1),muted:!!req.body.muted,videoId:req.body.videoId||null,updatedAt:Date.now()};if(cloudPlayerState.error)console.log("cloud player error",cloudPlayerState.error);}res.json({ok:true});});
app.post("/api/action/:action",auth,(req,res)=>{const a=req.params.action;let r={ok:true,message:"OK"};if(a==="next")nextVideo(1);else if(a==="prev")nextVideo(-1);else if(a==="play"){playing=true;io.emit("playback",{playing});r.message="Gameplay playing";}else if(a==="pause"){playing=false;io.emit("playback",{playing});r.message="Gameplay paused";}else if(a==="start")r=startBroadcast();else if(a==="stop")r=stopBroadcast();else if(a==="test-on"||a==="test-off"||a==="reaction-test")r={ok:false,message:"Facecam/voice test mode is disabled. This build is gameplay-only."};else return res.status(404).json({ok:false,message:"Unknown action"});res.json({...r,state:state()});});
app.post("/api/video-ended",auth,(req,res)=>{if(req.body.videoId===cur().id)nextVideo(1);res.json(state());});
app.get("/api/cloud-frame",auth,(req,res)=>{res.setHeader("Cache-Control","no-store");if(!fs.existsSync("/tmp/cloud-frame.jpg"))return res.status(503).send("Cloud frame not ready");res.sendFile("/tmp/cloud-frame.jpg");});
io.on("connection",s=>s.emit("status",state()));
server.listen(PORT,"0.0.0.0",()=>{console.log(`Takarada gameplay-only live on :${PORT}`);if(process.env.AUTO_START==="true"&&getRtmp())setTimeout(startBroadcast,7000);});
