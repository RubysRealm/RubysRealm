import http from 'node:http';
import https from 'node:https';
import {pathToFileURL} from 'node:url';

// The existing chart and database remain the sole source of market data.
// No credentials, cookies, response cache, or prediction engine live here.
export function createGateway({upstream, publicOrigin, discordOrigin}) {
  const base = new URL(upstream);
  const transport = base.protocol === 'https:' ? https : http;
  const agent = new transport.Agent({keepAlive:true});
  const reads = new Set(['market','candles','short-candles','ticker','time','settlements','kalshi-stream','kalshi-connection','worker-state','round-study']);
  return http.createServer((req,res) => {
    const fail = (code,message) => { if(!res.headersSent)res.writeHead(code,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify({error:message})); };
    let path;
    try { path = new URL(req.url,publicOrigin); } catch { return fail(400,'Invalid request'); }
    if(path.origin !== publicOrigin)return fail(400,'Invalid request');
    if(path.pathname === '/healthz'){res.writeHead(200,{'cache-control':'no-store'});return res.end('ok');}
    const method=req.method;
    const interaction=path.pathname === '/api/discord/interactions';
    const update=path.pathname === '/api/round-study' && method === 'POST';
    const read=method === 'GET' || method === 'HEAD';
    if(!read && !update && !(interaction && method==='POST'))return fail(405,'Read-only public chart');
    if(path.pathname.startsWith('/api/') && !reads.has(path.pathname.slice(5)) && !interaction)return fail(404,'Unknown endpoint');
    if(!path.pathname.startsWith('/api/') && !(/^\/(?:$|assets\/|_next\/|discord\/|favicon|icon|robots\.txt)/.test(path.pathname)))return fail(404,'Unknown resource');
    const origin=req.headers.origin;
    if(update && origin && origin!==publicOrigin && origin!==discordOrigin)return fail(403,'Origin not allowed');
    const headers={'accept-encoding':'identity'};
    for(const key of ['accept','content-type','last-event-id','x-signature-ed25519','x-signature-timestamp'])if(req.headers[key])headers[key]=req.headers[key];
    if(update && origin)headers.origin=base.origin;
    // Build the path against a fixed origin, never a caller-supplied target.
    const target=new URL(base.origin); target.pathname=path.pathname;target.search=path.search;
    const proxy=transport.request(target,{method,headers,agent},up=>{
      if(up.statusCode>=300 && up.statusCode<400){up.resume();return fail(502,'Chart temporarily unavailable');}
      const out={'cache-control':'no-store, max-age=0','x-accel-buffering':'no','referrer-policy':'no-referrer'};
      for(const key of ['content-type','content-length','content-encoding','vary'])if(up.headers[key])out[key]=up.headers[key];
      res.writeHead(up.statusCode||502,out);res.flushHeaders();up.pipe(res);
      up.on('error',()=>res.destroy());
    });
    proxy.setTimeout(30000,()=>proxy.destroy());
    proxy.on('error',()=>fail(502,'Chart feed reconnecting'));
    let size=0;
    req.on('data',chunk=>{size+=chunk.length;if(size>65536){proxy.destroy();req.destroy();}});
    req.pipe(proxy);
    res.on('close',()=>proxy.destroy());
  });
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href){
  const upstream=process.env.CHART_ORIGIN;
  const publicOrigin=process.env.PUBLIC_ORIGIN;
  if(!upstream?.startsWith('https://') || !publicOrigin?.startsWith('https://'))throw Error('HTTPS origins required');
  const server=createGateway({upstream,publicOrigin,discordOrigin:process.env.DISCORD_ORIGIN});
  server.listen(Number(process.env.PORT||10000),'0.0.0.0');
  process.on('SIGTERM',()=>{server.close();setTimeout(()=>process.exit(0),5000).unref();});
}
