const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const puppeteer = require('puppeteer-core');

const BASE = 'rubyclips';
const WORK = path.join(BASE, 'muffin_work');
const STATE_PATH = path.join(BASE, 'muffin_state.json');
const PACKING_TARGET_SECONDS = 590.0;
const LOOKAHEAD_EPISODES = 12;
const NETSHORT_SERIES = 'the-counterattack-of-the-fat-wife-queen-2092170996947619841';

const state = JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'));
const firstEpisode = Number(state.nextEpisode);
const episodeCount = Number(state.currentSeriesEpisodeCount);
if (!Number.isInteger(firstEpisode) || firstEpisode < 1 || firstEpisode > episodeCount) throw new Error(`No unresolved episode available: next=${firstEpisode}, total=${episodeCount}`);

fs.mkdirSync(WORK, { recursive: true });
for (const name of fs.readdirSync(WORK)) {
  if (/^ep\d+\.mp4$/.test(name) || ['episodes.json','selected.json','concat.txt'].includes(name)) { try { fs.unlinkSync(path.join(WORK, name)); } catch {} }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const chrome = ['/usr/bin/google-chrome','/usr/bin/chromium','/usr/bin/chromium-browser'].find(p => fs.existsSync(p));
const episodeUrl = episode => `https://netshort.com/episode/${NETSHORT_SERIES}-ep-${episode}`;
const durationOf = file => Number(execFileSync('ffprobe', ['-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1', file], {encoding:'utf8'}).trim());

function validDownloadedFile(file) {
  if (!fs.existsSync(file) || fs.statSync(file).size < 250000) return null;
  const dur = durationOf(file);
  return Number.isFinite(dur) && dur >= 10 ? dur : null;
}

function tryYtDlp(url, file) {
  try {
    execFileSync('yt-dlp', ['--no-playlist','--no-progress','--retries','3','--fragment-retries','3','--add-header','Referer:https://netshort.com/','--add-header','User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36','-f','bv*+ba/b','--merge-output-format','mp4','--remux-video','mp4','-o',file,url], {stdio:'inherit'});
    return validDownloadedFile(file);
  } catch (e) {
    console.error(`yt-dlp failed for ${url}: ${e.message}`);
    try { if (fs.existsSync(file)) fs.unlinkSync(file); } catch {}
    return null;
  }
}

async function browserMedia(url, episode) {
  if (!chrome) return null;
  const browser = await puppeteer.launch({headless:true, executablePath:chrome, args:['--no-sandbox','--disable-dev-shm-usage','--autoplay-policy=no-user-gesture-required','--disable-blink-features=AutomationControlled']});
  try {
    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36');
    await page.evaluateOnNewDocument(() => Object.defineProperty(navigator, 'webdriver', {get:()=>undefined}));
    const candidates=[];
    const add=u=>{const s=String(u||''); if(!s||s.startsWith('blob:')||s.startsWith('data:'))return; if(!/\.m3u8(?:[?&#]|$)|\.mp4(?:[?&#]|$)|\/video\/|vod|play/i.test(s))return; if(/cover|poster|image/i.test(s))return; if(!candidates.includes(s))candidates.push(s);};
    page.on('request', req=>{if(req.resourceType()==='media')add(req.url());});
    page.on('response', resp=>{const h=resp.headers()||{}; const ct=String(h['content-type']||'').toLowerCase(); if(ct.startsWith('video/')||ct.includes('mpegurl'))add(resp.url());});
    await page.goto(url,{waitUntil:'domcontentloaded',timeout:90000});
    await sleep(4000);
    await page.evaluate(async()=>{const v=document.querySelector('video'); if(v){try{v.muted=true; await v.play();}catch{}}}).catch(()=>{});
    await sleep(8000);
    const info=await page.evaluate(()=>{const v=document.querySelector('video'); return {currentSrc:v?.currentSrc||'',src:v?.src||'',resources:performance.getEntriesByType('resource').map(x=>x.name)};});
    add(info.currentSrc); add(info.src); for(const r of info.resources)add(r);
    const cookies=await page.cookies().catch(()=>[]);
    console.log(`Episode ${episode}: captured ${candidates.length} NetShort media candidates.`);
    return {candidates,cookieHeader:cookies.map(c=>`${c.name}=${c.value}`).join('; ')};
  } catch(e) { console.error(`NetShort browser capture failed for Episode ${episode}: ${e.message}`); return null; }
  finally { await browser.close(); }
}

function tryDirectMedia(media, referer, cookieHeader, file) {
  try {
    const args=['-L','--fail','--retry','3','--retry-delay','1','--connect-timeout','25','-A','Mozilla/5.0','-e',referer];
    if(cookieHeader)args.push('-H',`Cookie: ${cookieHeader}`);
    args.push(media,'-o',file);
    execFileSync('curl',args,{stdio:'inherit'});
    const dur=validDownloadedFile(file); if(dur)return dur;
  } catch(e) { console.error(`Direct media download failed: ${e.message}`); }
  try { if(fs.existsSync(file))fs.unlinkSync(file); } catch {}
  return null;
}

async function acquireEpisode(episode) {
  const url=episodeUrl(episode); const file=path.join(WORK,`ep${episode}.mp4`);
  let dur=tryYtDlp(url,file);
  if(dur)return {episode,sourceUrl:url,shortDramaUrl:url,videoId:`netshort-ep-${episode}`,sourceHint:'netshort-yt-dlp',file,duration:dur};
  const captured=await browserMedia(url,episode);
  if(captured){for(const media of captured.candidates.slice().reverse()){dur=tryDirectMedia(media,url,captured.cookieHeader,file); if(dur)return {episode,sourceUrl:url,shortDramaUrl:url,videoId:`netshort-ep-${episode}`,sourceHint:'netshort-browser-media',file,duration:dur};}}
  throw new Error(`Episode ${episode}: unable to acquire full NetShort media.`);
}

(async()=>{
  const resolved=[]; let packedSeconds=0; const last=Math.min(episodeCount,firstEpisode+LOOKAHEAD_EPISODES-1);
  for(let episode=firstEpisode;episode<=last;episode++){
    let item; try{item=await acquireEpisode(episode);}catch(e){if(!resolved.length)throw e; console.error(`Stopping lookahead at Episode ${episode}: ${e.message}`); break;}
    if(resolved.length&&packedSeconds+item.duration>PACKING_TARGET_SECONDS){try{fs.unlinkSync(item.file);}catch{} console.log(`Episode ${episode} would exceed ${PACKING_TARGET_SECONDS}s; Part ${state.nextPart} is full.`); break;}
    resolved.push(item); packedSeconds+=item.duration; console.log(`Resolved Episode ${episode} via ${item.sourceHint}: ${item.duration.toFixed(2)}s; packed=${packedSeconds.toFixed(2)}s`); if(packedSeconds>=PACKING_TARGET_SECONDS)break;
  }
  if(!resolved.length||Number(resolved[0].episode)!==firstEpisode)throw new Error(`Alternate resolver did not produce required Episode ${firstEpisode}.`);
  fs.writeFileSync(path.join(WORK,'episodes.json'),JSON.stringify(resolved,null,2)+'\n');
  console.log(`Prepared ${resolved.length} consecutive NetShort episodes starting at ${firstEpisode}; ${packedSeconds.toFixed(2)} seconds.`);
})().catch(err=>{console.error(err);process.exit(1);});
