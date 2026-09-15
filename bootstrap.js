import './server.js';
const port=process.env.PORT||10000;
const token=process.env.CONTROL_TOKEN||'change-me';
const headers={'Content-Type':'application/json','x-control-token':token};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
for(let i=0;i<30;i++){
 try{
  const r=await fetch(`http://127.0.0.1:${port}/api/state`);
  if(r.ok){await fetch(`http://127.0.0.1:${port}/api/action/test-off`,{method:'POST',headers,body:'{}'}).catch(()=>{});break;}
 }catch{}
 await pause(1000);
}
