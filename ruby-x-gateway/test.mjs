import http from 'node:http';
import assert from 'node:assert/strict';
import {createGateway} from './server.mjs';
let received;
const upstream=http.createServer((req,res)=>{
 received={url:req.url,headers:req.headers};
 if(req.url==='/api/kalshi-stream'){
   res.writeHead(200,{'content-type':'text/event-stream'});res.write('data: live\n\n');
   return setTimeout(()=>res.end('data: next\n\n'),150);
 }
 if(req.url==='/assets/redirect'){res.writeHead(302,{location:'https://private.invalid'});return res.end();}
 res.writeHead(200,{'content-type':'application/json','set-cookie':'secret=never-forward','cache-control':'public,max-age=999'});
 res.end(JSON.stringify({live:true}));
});
await new Promise(r=>upstream.listen(0,'127.0.0.1',r));
const upstreamOrigin='http://127.0.0.1:'+upstream.address().port;
const gateway=createGateway({upstream:upstreamOrigin,publicOrigin:'https://ruby-x-terminal.onrender.com',discordOrigin:'https://1563285254918115348.discordsays.com'});
await new Promise(r=>gateway.listen(0,'127.0.0.1',r));
const origin='http://127.0.0.1:'+gateway.address().port;
try{
 let r=await fetch(origin+'/api/market?asset=ETH',{headers:{cookie:'private=1',authorization:'Bearer private'}});
 assert.equal(r.status,200);assert.equal(r.headers.get('set-cookie'),null);assert.match(r.headers.get('cache-control'),/no-store/);
 assert.equal(received.url,'/api/market?asset=ETH');assert.equal(received.headers.cookie,undefined);assert.equal(received.headers.authorization,undefined);
 assert.equal((await fetch(origin+'/api/kalshi-connection',{method:'POST'})).status,405);
 assert.equal((await fetch(origin+'/api/round-study',{method:'POST',headers:{origin:'https://evil.invalid'}})).status,403);
 assert.equal((await fetch(origin+'/api/round-study?asset=BTC',{method:'POST',headers:{origin:'https://ruby-x-terminal.onrender.com'}})).status,200);
 assert.equal(received.headers.origin,upstreamOrigin);
 assert.equal((await fetch(origin+'/assets/redirect')).status,502);
 r=await fetch(origin+'/api/kalshi-stream');
 const reader=r.body.getReader();const first=await reader.read();assert.match(new TextDecoder().decode(first.value),/data: live/);assert.equal(first.done,false);await reader.cancel();
 console.log('PASS: live streaming, no cache, shared asset requests, no credential forwarding, origin validation, read-only management, redirect privacy');
}finally{gateway.closeAllConnections();upstream.closeAllConnections();gateway.close();upstream.close();}
