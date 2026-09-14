import express from "express";
import http from "http";
import { Server as SocketIOServer } from "socket.io";
import { spawn } from "child_process";
import fs from "fs";

const app = express();
const server = http.createServer(app);
const io = new SocketIOServer(server,{cors:{origin:"*"}});
const PORT = Number(process.env.PORT||10000);
const CONTROL_TOKEN = process.env.CONTROL_TOKEN||"change-me";
const TIKTOK_USERNAME = (process.env.TIKTOK_USERNAME||"").replace(/^@/,"").trim();
const videos = [
["c6FAO3-zvhE","Lush Caves"],["AirXwBsNPDw","Rainy Riverside"],["wcIUiy_Ofcw","Ghibli Nostalgic"],["y8yMP36qHXA","Rainy Swamp"],["Zoq4ogt2wtU","Pine Forest House"],["Dy3VtjcHdCs","Rainy Cliff"],["ykHsq6yUNGg","Rainy Flower Forest"],["nUbDQ0wUESU","Medieval Farmhouse"],["snvLyjMcgh0","Rainy River"],["N6S53tOB1ss","Rainy Jungle Tree House"],["C_WaC-JmhFo","Rainy Mountain"],["eHSxedwXaM0","Rainy Cherry Grove"],["oCIpgdb2pM4","Rainy Mangrove Swamp"],["yTTutYKV1rk","Rainy Overgrown Laputa Part 1"],["2byiUUc0SnQ","Rainy Overgrown Laputa Part 2"],["UDRhiTUMVQY","Ghibli Nostalgic 1.20"],["wV9VatPiPf4","Rainy Spruce Island"],["LoeTtwvBD_k","Rainy Beach House"],["-DRRSTrLHTI","Rainy Greenhouse"],["bp-1X7sQ_2M","Rainy Cherry Lake"],["Ps0oA1nt3mw","Rainy Meadow"],["pW0iacBW1MU","Snowy Mountain"],["Az9X6YFzcBU","Christmas Snow Village"],["i9U-rUObowg","Rainy Mountain 1.21"],["IsXCRoImZ3c","Rainy Pale Garden"],["AepZzZS6j_U","Rainy Dark Forest"],["GFmBMg7-b44","Rainy Farmhouse"],["CIHsdaqCXwM","Rainy River Island"],["hYJY95sAeFc","Rainy Pale Cherry"],["O6yrzYkn2i8","Rainy Old Treehouse"]].map(([id,title])=>({id,title}));

let index=0,playing=true,ffmpeg=null,tiktokConnected=false,recentChat=[],recentEvents=[];
let cloudPlayerState={code:-999,label:"waiting",videoId:null,updatedAt:0};
let speaking=false;
app.use(express.json());
app.use(express.static("public"));

function auth(req,res,next){const t=req.query.token||req.headers["x-control-token"];if(t!==CONTROL_TOKEN)return res.status(403).send("Bad control token");next()}
function cur(){return videos[index]}
function state(){return {index,count:videos.length,playing,current:cur(),next:videos[(index+1)%videos.length],broadcasting:!!ffmpeg,tiktokConnected,username:TIKTOK_USERNAME||null,cloudPlayerState,chat:recentChat.slice(-8),events:recentEvents.slice(-8)}}
function nextVideo(d=1){index=(index+d+videos.length)%videos.length;playing=true;io.emit("queue",state())}
function addChat(user,text){const c={user,text,ts:Date.now()};recentChat.push(c);recentChat=recentChat.slice(-50);io.emit("chat",c)}
function speak(text){if(speaking||!text)return;speaking=true;const f=`/tmp/takarada-${Date.now()}.wav`;const synth=spawn("espeak-ng",["-v","en-us","-s","155","-p","48","-a","135","-w",f,text]);synth.on("close",()=>{const p=spawn("paplay",["--device=takarada",f]);p.on("close",()=>{speaking=false;try{fs.unlinkSync(f)}catch{}});p.on("error",()=>{speaking=false;try{fs.unlinkSync(f)}catch{}})});synth.on("error",()=>{speaking=false})}
function addEvent(type,text,extra={}){const e={type,text,ts:Date.now(),...extra};recentEvents.push(e);recentEvents=recentEvents.slice(-50);io.emit("event",e);if(type==="commentary")speak(text);if(type==="follow")speak("Thanks for the follow.");if(type==="gift")speak("Yo, thank you for the gift.")}
function commentary(title){const t=title.toLowerCase();let p;if(t.includes("cave"))p=["These caves are actually coming together.","The lighting down here is clean.","I would absolutely get lost in this cave."];else if(t.includes("rain"))p=["The rain makes this build way more relaxing.","This is a good spot for a rainy build.","That roof is going to look good in this weather."];else if(t.includes("snow")||t.includes("christmas"))p=["This snow build is ridiculously cozy.","The winter atmosphere is perfect.","I like where this village is going."];else p=["That build is coming together.","I like this spot.","This is actually relaxing to watch."];return p[Math.floor(Math.random()*p.length)]}
function startBroadcast(){if(ffmpeg)return {ok:true,message:"Broadcast already running"};const rtmp=process.env.RTMP_URL;if(!rtmp)return {ok:false,message:"RTMP_URL is not configured yet"};const w=process.env.STREAM_WIDTH||"720",h=process.env.STREAM_HEIGHT||"1280",fps=process.env.STREAM_FPS||"30";const args=["-hide_banner","-loglevel","warning","-thread_queue_size","1024","-f","x11grab","-draw_mouse","0","-framerate",fps,"-video_size",`${w}x${h}`,"-i",":99.0","-thread_queue_size","1024","-f","pulse","-i","takarada.monitor","-c:v","libx264","-preset","veryfast","-tune","zerolatency","-pix_fmt","yuv420p","-b:v","3500k","-maxrate","4000k","-bufsize","7000k","-g",String(Number(fps)*2),"-c:a","aac","-b:a","128k","-ar","44100","-f","flv",rtmp];ffmpeg=spawn("ffmpeg",args,{stdio:["ignore","ignore","pipe"]});ffmpeg.stderr.on("data",d=>console.log("[ffmpeg]",String(d).trim()));ffmpeg.on("exit",c=>{console.log("ffmpeg exited",c);ffmpeg=null;io.emit("status",state())});io.emit("status",state());return {ok:true,message:"Cloud broadcast started"}}
function stopBroadcast(){if(!ffmpeg)return {ok:true,message:"Broadcast already stopped"};ffmpeg.kill("SIGTERM");ffmpeg=null;io.emit("status",state());return {ok:true,message:"Cloud broadcast stopped"}}
async function connectTikTok(){if(!TIKTOK_USERNAME)return;try{const mod=await import("tiktok-live-connector");const TikTokLiveConnection=mod.TikTokLiveConnection;const WebcastEvent=mod.WebcastEvent;if(!TikTokLiveConnection||!WebcastEvent)throw new Error("TikTok connector API unavailable");const t=new TikTokLiveConnection(TIKTOK_USERNAME,{processInitialData:false});t.on(WebcastEvent.CHAT,d=>addChat(d.user?.uniqueId||d.uniqueId||d.user?.nickname||"viewer",d.comment||""));t.on(WebcastEvent.FOLLOW,d=>addEvent("follow",`${d.user?.uniqueId||d.uniqueId||d.user?.nickname||"viewer"} followed`));t.on(WebcastEvent.GIFT,d=>{const user=d.user?.uniqueId||d.uniqueId||d.user?.nickname||"viewer";const gift=d.giftDetails?.giftName||d.giftName||`gift ${d.giftId||""}`.trim();addEvent("gift",`${user} sent ${gift}`,{gift})});await t.connect();tiktokConnected=true;io.emit("status",state())}catch(e){console.log("TikTok event connection unavailable:",e?.message||e);tiktokConnected=false}}

app.get("/",(req,res)=>res.redirect("/control?token="+encodeURIComponent(CONTROL_TOKEN)));
app.get("/stage",(req,res)=>res.sendFile(process.cwd()+"/public/stage.html"));
app.get("/preview",(req,res)=>res.sendFile(process.cwd()+"/public/stage.html"));
app.get("/control",auth,(req,res)=>res.sendFile(process.cwd()+"/public/control.html"));
app.get("/api/state",(req,res)=>res.json(state()));
app.post("/api/player-state",(req,res)=>{if(req.body?.renderer==="cloud"){cloudPlayerState={code:Number(req.body.code),label:String(req.body.label||"unknown"),videoId:req.body.videoId||null,updatedAt:Date.now()}}res.json({ok:true})});
app.post("/api/action/:action",auth,(req,res)=>{const a=req.params.action;let r={ok:true,message:"OK"};if(a==="next")nextVideo(1);else if(a==="prev")nextVideo(-1);else if(a==="play"){playing=true;io.emit("playback",{playing})}else if(a==="pause"){playing=false;io.emit("playback",{playing})}else if(a==="start")r=startBroadcast();else if(a==="stop")r=stopBroadcast();else return res.status(404).json({ok:false,message:"Unknown action"});res.json({...r,state:state()})});
app.post("/api/video-ended",(req,res)=>{nextVideo(1);res.json(state())});
io.on("connection",s=>s.emit("status",state()));
function scheduleComment(){const delay=90000+Math.floor(Math.random()*110000);setTimeout(()=>{addEvent("commentary",commentary(cur().title));scheduleComment()},delay)}
scheduleComment();
server.listen(PORT,"0.0.0.0",()=>{console.log(`Takarada cloud live on :${PORT}`);connectTikTok();if(process.env.AUTO_START==="true"&&process.env.RTMP_URL)setTimeout(startBroadcast,7000)});
