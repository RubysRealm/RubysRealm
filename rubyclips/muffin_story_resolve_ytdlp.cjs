const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const BASE='rubyclips';
const WORK=path.join(BASE,'muffin_work');
const STATE_PATH=path.join(BASE,'muffin_state.json');
const MAX_SECONDS=590;
const LOOKAHEAD=12;
const AUTHOR='muffindrama_us';
const IDS={
  39:'7682997046713781518',
  40:'7682997059560951054',
  41:'7682997068738071822',
  42:'7682997029441703182',
  43:'7682997049444289805',
  44:'7682997046084685069',
  45:'7682997097267809550',
  46:'7682997091664235790',
  47:'7682997037314395406',
  48:'7682997041479388429'
};
const s=JSON.parse(fs.readFileSync(STATE_PATH,'utf8'));
const first=Number(s.nextEpisode), total=Number(s.currentSeriesEpisodeCount);
if(!Number.isInteger(first)||first<1||first>total) throw new Error(`Bad nextEpisode ${first}`);
fs.mkdirSync(WORK,{recursive:true});
for(const n of fs.readdirSync(WORK)){if(/^ep\d+\.mp4$/.test(n)||['episodes.json','selected.json','concat.txt'].includes(n)){try{fs.unlinkSync(path.join(WORK,n))}catch{}}}
function duration(f){return Number(execFileSync('ffprobe',['-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',f],{encoding:'utf8'}).trim())}
function streams(f){return execFileSync('ffprobe',['-v','error','-show_entries','stream=codec_type','-of','csv=p=0',f],{encoding:'utf8'}).trim().split(/\s+/)}
function acquire(ep){
  const id=IDS[ep]; if(!id) throw new Error(`Episode ${ep}: no canonical ID mapped`);
  const url=`https://www.tiktok.com/@${AUTHOR}/video/${id}`;
  const out=path.join(WORK,`ep${ep}.mp4`);
  const ua='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36';
  const attempts=[
    ['--no-playlist','--no-progress','--retries','5','--fragment-retries','5','--user-agent',ua,'--referer','https://www.tiktok.com/','-f','bv*+ba/b','--merge-output-format','mp4','--remux-video','mp4','-o',out,url],
    ['--no-playlist','--no-progress','--retries','5','--user-agent',ua,'--referer','https://www.tiktok.com/','-f','b','--remux-video','mp4','-o',out,url]
  ];
  let err;
  for(const args of attempts){
    try{
      try{if(fs.existsSync(out))fs.unlinkSync(out)}catch{}
      execFileSync('yt-dlp',args,{stdio:'inherit'});
      const size=fs.existsSync(out)?fs.statSync(out).size:0;
      if(size<500000) throw new Error(`file too small ${size}`);
      const d=duration(out); if(!Number.isFinite(d)||d<10) throw new Error(`bad duration ${d}`);
      const ss=streams(out); if(!ss.includes('video')||!ss.includes('audio')) throw new Error(`missing A/V streams: ${ss.join(',')}`);
      console.log(`Episode ${ep} -> ${id} via yt-dlp ${d.toFixed(2)}s`);
      return {episode:ep,sourceUrl:url,shortDramaUrl:`https://www.tiktok.com/shortdrama/episode/${s.currentSeriesId}/${ep}`,videoId:id,sourceHint:'canonical-id-yt-dlp',file:out,duration:d};
    }catch(e){err=e; console.error(`Episode ${ep} yt-dlp attempt failed: ${e.message}`)}
  }
  try{if(fs.existsSync(out))fs.unlinkSync(out)}catch{}
  throw new Error(`Episode ${ep}: yt-dlp failed: ${err?.message||'unknown'}`);
}
const resolved=[]; let seconds=0;
for(let ep=first;ep<=Math.min(total,first+LOOKAHEAD-1);ep++){
  let item; try{item=acquire(ep)}catch(e){if(!resolved.length)throw e; console.error(`Stopping at ${ep}: ${e.message}`); break}
  if(resolved.length&&seconds+item.duration>MAX_SECONDS){try{fs.unlinkSync(item.file)}catch{}; break}
  resolved.push(item); seconds+=item.duration; if(seconds>=MAX_SECONDS)break;
}
if(!resolved.length||resolved[0].episode!==first) throw new Error(`Did not produce Episode ${first}`);
fs.writeFileSync(path.join(WORK,'episodes.json'),JSON.stringify(resolved,null,2)+'\n');
console.log(`Prepared ${resolved.length} episodes from ${first}; ${seconds.toFixed(2)}s total.`);
