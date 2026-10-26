import http from 'node:http';
import https from 'node:https';
import {pathToFileURL} from 'node:url';
import {startAutoRoles} from './autoroles.mjs';

// The chart owns predictions, credentials and durable statistics.
// A bounded public Coinbase cache shares market-data requests across viewers.
export function createGateway({upstream, publicOrigin, discordOrigin}) {
  const base = new URL(upstream);
  const transport = base.protocol === 'https:' ? https : http;
  const agent = new transport.Agent({keepAlive:true});
  const coinbase=createCoinbaseSource();
  const reads = new Set(['market','candles','short-candles','ticker','time','settlements','kalshi-stream','kalshi-connection','worker-state','round-study']);
  return http.createServer((req,res) => {
    const fail = (code,message) => { if(!res.headersSent)res.writeHead(code,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify({error:message})); };
    let path;
    try { path = new URL(req.url,publicOrigin); } catch { return fail(400,'Invalid request'); }
    if(path.origin !== publicOrigin)return fail(400,'Invalid request');
    if(path.pathname === '/api/coinbase-source'){
      if(req.method!=='GET')return fail(405,'Read-only public feed');
      if([...path.searchParams.keys()].some(k=>k!=='path')||path.searchParams.getAll('path').length!==1)return fail(400,'Invalid request');
      void coinbase(path.searchParams.get('path')).then(value=>{if(res.destroyed)return;res.writeHead(value.status,{'cache-control':'no-store',...value.headers});res.end(value.body);}).catch(()=>fail(503,'Feed unavailable'));
      return;
    }
    if(path.pathname === '/healthz'){res.writeHead(200,{'cache-control':'no-store'});return res.end('ok');}
    const method=req.method;
    const interaction=path.pathname === '/api/discord/interactions';
    const memberAuth=['/auth/discord/start','/auth/discord/callback','/auth/discord/logout','/auth/discord/redeem','/auth/discord/link-preview'].includes(path.pathname);
    const memberApi=['/api/member/session','/api/member/connection'].includes(path.pathname);
    const memberWrite=(path.pathname==='/api/member/connection'&&['POST','DELETE'].includes(method))||(['/auth/discord/logout','/auth/discord/redeem','/auth/discord/link-preview'].includes(path.pathname)&&method==='POST');
    const update=path.pathname === '/api/round-study' && method === 'POST';
    const read=method === 'GET' || method === 'HEAD';
    if(!read && !update && !memberWrite && !(interaction && method==='POST'))return fail(405,'Read-only public chart');
    if(path.pathname.startsWith('/api/') && !reads.has(path.pathname.slice(5)) && !interaction && !memberApi)return fail(404,'Unknown endpoint');
    if(!path.pathname.startsWith('/api/') && !memberAuth && path.pathname!=='/members' && !(/^\/(?:$|assets\/|_next\/|discord\/|favicon|icon|robots\.txt)/.test(path.pathname)))return fail(404,'Unknown resource');
    const origin=req.headers.origin;
    if(update && origin && origin!==publicOrigin && origin!==discordOrigin)return fail(403,'Origin not allowed');
    if(memberWrite && origin!==publicOrigin)return fail(403,'Origin not allowed');
    const headers={'accept-encoding':'identity'};
    // Forward only our opaque session/state cookies; never spoofed identity headers.
    const cookies=(req.headers.cookie??'').split(';').map(x=>x.trim()).filter(x=>/^__Host-ruby-(session|oauth)=[A-Za-z0-9_-]{43}$/.test(x));
    if(cookies.length)headers.cookie=cookies.join('; ');
    if(memberWrite)headers.origin=origin;
    for(const key of ['accept','content-type','last-event-id','x-signature-ed25519','x-signature-timestamp'])if(req.headers[key])headers[key]=req.headers[key];
    if(update && origin)headers.origin=base.origin;
    // Build the path against a fixed origin, never a caller-supplied target.
    const target=new URL(base.origin); target.pathname=path.pathname;target.search=path.search;
    const proxy=transport.request(target,{method,headers,agent},up=>{
      if(up.statusCode>=300 && up.statusCode<400){
        const location=up.headers.location;let destination;
        try{destination=new URL(location,base.origin);}catch{up.resume();return fail(502,'Invalid redirect');}
        const local=destination.origin===base.origin||destination.origin===publicOrigin;
        const oauth=memberAuth&&destination.origin==='https://discord.com'&&destination.pathname==='/oauth2/authorize';
        if(!local&&!oauth){up.resume();return fail(502,'Invalid redirect');}
        const redirect=local?publicOrigin+destination.pathname+destination.search:destination.href;
        const cookies=(up.headers['set-cookie']??[]).filter(x=>/^__Host-ruby-(session|oauth)=/.test(x));
        up.resume();res.writeHead(up.statusCode,{'location':redirect,'cache-control':'private, no-store','referrer-policy':'no-referrer',...(cookies.length?{'set-cookie':cookies}:{})});return res.end();
      }
      const out={'cache-control':'no-store, max-age=0','x-accel-buffering':'no','referrer-policy':'no-referrer'};
      for(const key of ['content-type','content-length','content-encoding','vary','x-frame-options','x-content-type-options'])if(up.headers[key])out[key]=up.headers[key];
      const sessionCookies=(up.headers['set-cookie']??[]).filter(x=>/^__Host-ruby-(session|oauth)=/.test(x));
      if(sessionCookies.length)out['set-cookie']=sessionCookies;
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

export function createCoinbaseSource({fetcher=fetch,clock=Date.now,pause=ms=>new Promise(r=>setTimeout(r,ms))}={}){
  const cache=new Map(),pending=new Map();let nextStart=0,retryAt=0;
  function validate(raw){
    const u=new URL(raw,'https://api.exchange.coinbase.com');
    if(u.origin!=='https://api.exchange.coinbase.com'||!/^\/products\/(BTC|ETH|XRP|SOL)-USD\/(ticker|candles|trades)$/.test(u.pathname))throw Error('Unsupported feed');
    const kind=u.pathname.split('/').at(-1),allowed=kind==='candles'?['start','end','granularity']:kind==='trades'?['limit','after']:[];
    for(const key of u.searchParams.keys())if(!allowed.includes(key)||u.searchParams.getAll(key).length!==1)throw Error('Invalid parameters');
    if(kind==='candles'){
      const start=Date.parse(u.searchParams.get('start')),end=Date.parse(u.searchParams.get('end'));
      if(u.searchParams.get('granularity')!=='60'||!Number.isFinite(start)||!Number.isFinite(end)||start>=end||end-start>299*60000||start<clock()-7*3600000||end>clock()+1000)throw Error('Invalid candle window');
    }
    if(kind==='trades'&&(u.searchParams.get('limit')!=='1000'||(u.searchParams.has('after')&&!/^\d{1,25}$/.test(u.searchParams.get('after')))))throw Error('Invalid trade page');
    u.searchParams.sort();return {url:u.href,kind};
  }
  return async raw=>{
    let url,kind;try{({url,kind}=validate(raw));}catch{return {status:400,body:'{"error":"Unsupported public feed request"}',headers:{}};}
    const hit=cache.get(url);if(hit&&hit.until>clock())return hit.value;
    if(pending.has(url))return pending.get(url);
    if(retryAt>clock())return {status:429,body:'{"error":"Coinbase cooldown"}',headers:{'retry-after':String(Math.ceil((retryAt-clock())/1000))}};
    if(pending.size>=16)return {status:503,body:'{"error":"Feed refresh queued"}',headers:{'retry-after':'1'}};
    const slot=Math.max(clock(),nextStart);nextStart=slot+220;
    const job=(async()=>{
      if(slot>clock())await pause(slot-clock());
      if(retryAt>clock())return {status:429,body:'{"error":"Coinbase cooldown"}',headers:{'retry-after':String(Math.ceil((retryAt-clock())/1000))}};
      try{
        const r=await fetcher(url,{headers:{Accept:'application/json','User-Agent':'RUBY-X-Market-Data/1.0'},signal:AbortSignal.timeout(4000)}),body=await r.text();
        const headers={'content-type':'application/json'};
        for(const k of ['date','age','retry-after','cb-after'])if(r.headers.has(k))headers[k]=r.headers.get(k);
        const value={status:r.status,body,headers};
        if(r.status===429){const raw=r.headers.get('retry-after'),n=Number(raw);retryAt=clock()+Math.max(1000,raw&&Number.isFinite(n)?n*1000:30000);}
        if(r.ok){if(cache.size>=256)cache.delete(cache.keys().next().value);cache.set(url,{value,until:clock()+(kind==='ticker'?1000:kind==='candles'?5000:1500)});}
        return value;
      }catch{return {status:503,body:'{"error":"Coinbase feed unavailable"}',headers:{'retry-after':'2'}};}
    })();pending.set(url,job);try{return await job;}finally{pending.delete(url);}
  };
}

if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href){
  const upstream=process.env.CHART_ORIGIN;
  const publicOrigin=process.env.PUBLIC_ORIGIN;
  if(!upstream?.startsWith('https://') || !publicOrigin?.startsWith('https://'))throw Error('HTTPS origins required');
  const server=createGateway({upstream,publicOrigin,discordOrigin:process.env.DISCORD_ORIGIN});
  server.listen(Number(process.env.PORT||10000),'0.0.0.0');
  startAutoRoles(process.env.DISCORD_BOT_TOKEN);
  process.on('SIGTERM',()=>{server.close();setTimeout(()=>process.exit(0),5000).unref();});
}

