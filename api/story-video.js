import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import sharp from 'sharp';
import ffmpegStaticPath from 'ffmpeg-static';
import { EdgeTTS } from 'node-edge-tts';
import { createStory } from '../content/story-engine.js';

export const config = { maxDuration: 300 };

const WIDTH = 540;
const HEIGHT = 960;
const FPS = 30;
const FFMPEG = process.env.USE_SYSTEM_FFMPEG === '1' ? 'ffmpeg' : ffmpegStaticPath;
const MAN_URL = 'https://github.com/RubysRealm/RubysRealm/releases/download/characters-v1/man.png';
const WOMAN_URL = 'https://github.com/RubysRealm/RubysRealm/releases/download/characters-v1/woman.png';

function run(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(FFMPEG, args, { stdio:['ignore','ignore','pipe'] });
    let stderr = '';
    child.stderr.on('data', c => { stderr += c.toString(); });
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve() : reject(new Error(`ffmpeg ${code}: ${stderr.slice(-2500)}`)));
  });
}

function esc(s='') {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
}

function wrap(text, max=30, lines=4) {
  const words = String(text).trim().split(/\s+/); const out=[]; let cur='';
  for (const w of words) {
    const t = cur ? `${cur} ${w}` : w;
    if (t.length > max && cur) { out.push(cur); cur=w; } else cur=t;
  }
  if (cur) out.push(cur);
  return out.slice(0, lines);
}

async function fetchBuffer(url) {
  const r = await fetch(url, { redirect:'follow' });
  if (!r.ok) throw new Error(`asset fetch ${r.status}`);
  return Buffer.from(await r.arrayBuffer());
}

async function speech(text, voice, out) {
  const map = {
    onyx:'en-US-GuyNeural', echo:'en-US-AndrewNeural', nova:'en-US-JennyNeural', shimmer:'en-US-AvaNeural', alloy:'en-US-BrianNeural'
  };
  const tts = new EdgeTTS({ voice:map[voice] || 'en-US-AvaNeural', lang:'en-US', outputFormat:'audio-24khz-96kbitrate-mono-mp3', rate:'-4%', pitch:'default', volume:'default', timeout:30000 });
  await tts.ttsPromise(text, out);
}

function durationFromMp3Fallback(text) {
  return Math.max(2.2, String(text).trim().split(/\s+/).length / 2.45);
}

async function makePortrait(buffer, out, side='left', active=true) {
  const base = sharp(buffer).resize({ width:470, height:650, fit:'cover', position:'north' });
  const img = await base.png().toBuffer();
  const x = side === 'left' ? -35 : 105;
  const y = active ? 150 : 205;
  const w = active ? 470 : 395;
  const h = active ? 650 : 575;
  const resized = await sharp(img).resize(w,h,{fit:'cover',position:'north'}).png().toBuffer();
  const shadow = Buffer.from(`<svg width="540" height="960"><ellipse cx="270" cy="815" rx="185" ry="28" fill="#000" opacity=".38"/></svg>`);
  await sharp({ create:{width:WIDTH,height:HEIGHT,channels:4,background:{r:0,g:0,b:0,alpha:0}} })
    .composite([{input:shadow,left:0,top:0},{input:resized,left:x,top:y}]).png().toFile(out);
}

function sceneOverlay(story, scene, idx, speakerName, accent, speaking) {
  const title = wrap(story.title.toUpperCase(), 22, 2);
  const cap = wrap(scene.dialogue, 35, 5);
  const titleSvg = title.map((t,i)=>`<text x="270" y="${82+i*31}" text-anchor="middle" fill="${accent}" font-family="Arial" font-size="27" font-weight="900">${esc(t)}</text>`).join('');
  const capSvg = cap.map((t,i)=>`<text x="270" y="${770+i*34}" text-anchor="middle" fill="#fff" font-family="Arial" font-size="27" font-weight="900">${esc(t)}</text>`).join('');
  const pulse = speaking ? 1 : .45;
  const progress = Math.round(((idx+1)/story.scenes.length)*490);
  return Buffer.from(`<svg width="540" height="960" xmlns="http://www.w3.org/2000/svg">
    <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#08101d" stop-opacity=".18"/><stop offset="1" stop-color="#04070d" stop-opacity=".82"/></linearGradient></defs>
    <rect width="540" height="960" fill="url(#g)"/>
    <rect x="15" y="18" width="510" height="130" rx="20" fill="#05060a" opacity=".67"/>
    <text x="270" y="48" text-anchor="middle" fill="#fff" opacity=".78" font-family="Arial" font-size="16" font-weight="700" letter-spacing="4">RUBY'S REALM</text>
    ${titleSvg}
    <rect x="18" y="690" width="504" height="235" rx="26" fill="#05070c" opacity=".86" stroke="${accent}" stroke-opacity=".7" stroke-width="3"/>
    <circle cx="48" cy="728" r="8" fill="${accent}" opacity="${pulse}"/>
    <text x="66" y="735" fill="${accent}" font-family="Arial" font-size="20" font-weight="900">${esc(speakerName.toUpperCase())}</text>
    ${capSvg}
    <rect x="25" y="940" width="490" height="7" rx="4" fill="#fff" opacity=".18"/><rect x="25" y="940" width="${progress}" height="7" rx="4" fill="${accent}"/>
  </svg>`);
}

async function buildScene({ story, scene, index, man, woman, dir }) {
  const speaker = story.characters.find(c=>c.id===scene.speaker) || story.characters[0];
  const isA = speaker.id === 'A';
  const speakerBuffer = isA ? man : woman;
  const otherBuffer = isA ? woman : man;
  const speakerPng = path.join(dir,`speaker-${index}.png`);
  const otherPng = path.join(dir,`other-${index}.png`);
  const bgPng = path.join(dir,`frame-${index}.png`);
  const audioRaw = path.join(dir,`audio-${index}.mp3`);
  const clip = path.join(dir,`clip-${index}.mp4`);

  await Promise.all([
    makePortrait(speakerBuffer,speakerPng,isA?'left':'right',true),
    makePortrait(otherBuffer,otherPng,isA?'right':'left',false),
    speech(scene.dialogue,speaker.voice,audioRaw)
  ]);

  const speakerImg = await fs.readFile(speakerPng);
  const otherImg = await fs.readFile(otherPng);
  const accent = scene.mood === 'funny' ? '#F6C945' : ['#7DD3FC','#A78BFA','#F472B6','#34D399'][index%4];
  const overlay = sceneOverlay(story,scene,index,speaker.name,accent,true);

  await sharp({ create:{width:WIDTH,height:HEIGHT,channels:4,background:{r:9,g:13,b:22,alpha:1}} })
    .composite([
      { input:Buffer.from(`<svg width="540" height="960"><rect width="540" height="960" fill="#0b1220"/><circle cx="110" cy="320" r="260" fill="${accent}" opacity=".13"/><circle cx="505" cy="535" r="280" fill="#6d28d9" opacity=".11"/></svg>`), left:0, top:0 },
      { input:otherImg,left:0,top:0,blend:'over',opacity:.62 },
      { input:speakerImg,left:0,top:0,blend:'over' },
      { input:overlay,left:0,top:0 }
    ]).jpeg({quality:91}).toFile(bgPng);

  const estimated = durationFromMp3Fallback(scene.dialogue) + .45;
  await run(['-y','-loop','1','-i',bgPng,'-i',audioRaw,'-filter_complex',`[0:v]scale=560:995,crop=540:960:x='10+4*sin(t*1.6)':y='16+3*cos(t*1.3)',zoompan=z='min(zoom+0.0007,1.035)':d=1:s=540x960:fps=${FPS}[v]`,'-map','[v]','-map','1:a','-c:v','libx264','-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-shortest','-t',String(estimated),clip]);
  return clip;
}

async function concatClips(clips, out, dir) {
  const list = path.join(dir,'concat.txt');
  await fs.writeFile(list, clips.map(f=>`file '${f.replaceAll("'","'\\''")}'`).join('\n'));
  await run(['-y','-f','concat','-safe','0','-i',list,'-c','copy',out]);
}

export default async function handler(req,res) {
  if (!['GET','HEAD'].includes(req.method)) return res.status(405).end();
  const seed = String(req.query?.seed || new Date().toISOString().slice(0,10));
  const story = createStory(seed);
  if (req.method === 'HEAD') {
    res.setHeader('X-Rubys-Realm-Format','photoreal-human-v1');
    res.setHeader('X-Rubys-Realm-Branding','brand-only');
    res.setHeader('X-AI-Generated','true');
    return res.status(200).end();
  }

  const dir = await fs.mkdtemp(path.join(os.tmpdir(),'ruby-real-'));
  try {
    const [man,woman] = await Promise.all([fetchBuffer(MAN_URL),fetchBuffer(WOMAN_URL)]);
    const clips=[];
    for (let i=0;i<story.scenes.length;i++) clips.push(await buildScene({story,scene:story.scenes[i],index:i,man,woman,dir}));
    const out = path.join(dir,'story.mp4');
    await concatClips(clips,out,dir);
    const data = await fs.readFile(out);
    res.setHeader('Content-Type','video/mp4');
    res.setHeader('Content-Length',String(data.length));
    res.setHeader('Cache-Control','public, max-age=86400, s-maxage=31536000, immutable');
    res.setHeader('X-Rubys-Realm-Format','photoreal-human-v1');
    res.setHeader('X-Rubys-Realm-Branding','brand-only');
    res.setHeader('X-AI-Generated','true');
    res.setHeader('X-Rubys-Realm-Duration',String(story.targetSeconds || Math.round(story.targetMinutes*60)));
    return res.status(200).send(data);
  } catch (e) {
    console.error('realistic renderer failed',e);
    return res.status(500).json({ok:false,error:e.message});
  } finally {
    await fs.rm(dir,{recursive:true,force:true}).catch(()=>{});
  }
}
