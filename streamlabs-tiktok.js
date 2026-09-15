const BASE = "https://streamlabs.com/api/v5/slobs/tiktok";

function token(){ return (process.env.STREAMLABS_TOKEN || "").trim(); }
function headers(){
  return {
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) StreamlabsDesktop/1.20.4 Chrome/122.0.6261.156 Electron/29.3.1 Safari/537.36",
    "authorization": `Bearer ${token()}`,
    "accept": "application/json, text/plain, */*"
  };
}

export function streamlabsConfigured(){ return !!token(); }

async function jsonFetch(url, options={}){
  const r = await fetch(url, {...options, headers:{...headers(), ...(options.headers||{})}});
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); } catch { data = {raw:text}; }
  if(!r.ok) throw new Error(`Streamlabs HTTP ${r.status}: ${text.slice(0,400)}`);
  return data;
}

export async function getTikTokInfo(){
  if(!streamlabsConfigured()) throw new Error("STREAMLABS_TOKEN is not configured");
  return await jsonFetch(`${BASE}/info`);
}

export async function createTikTokLive({title="Relaxing Minecraft Longplay", category="", audienceType="0"}={}){
  if(!streamlabsConfigured()) throw new Error("STREAMLABS_TOKEN is not configured");
  const form = new FormData();
  form.append("title", title);
  form.append("device_platform", "win32");
  form.append("category", category);
  form.append("audience_type", audienceType);
  const data = await jsonFetch(`${BASE}/stream/start`, {method:"POST", body:form});
  if(!data?.rtmp || !data?.key) throw new Error(`Streamlabs did not return an RTMP destination: ${JSON.stringify(data).slice(0,500)}`);
  const server = String(data.rtmp).replace(/\/$/, "");
  const key = String(data.key).replace(/^\//, "");
  return {id:data.id || null, server, key, destination:`${server}/${key}`};
}

export async function endTikTokLive(roomId){
  if(!roomId || !streamlabsConfigured()) return {success:true};
  return await jsonFetch(`${BASE}/stream/${encodeURIComponent(roomId)}/end`, {method:"POST"});
}
