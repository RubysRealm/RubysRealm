import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import sharp from 'sharp';
import ffmpegStaticPath from 'ffmpeg-static';
import { createStory } from '../content/story-engine.js';
import { generateSpeechAudio } from '../lib/ai-gateway.js';

export const config = { maxDuration: 300 };

const WIDTH = 540;
const HEIGHT = 960;
const FPS = 30;
const MOUTH_STEP = 0.15;
const SCENE_GAP = 0.42;
const FFMPEG = process.env.USE_SYSTEM_FFMPEG === '1' ? 'ffmpeg' : ffmpegStaticPath;

function escapeXml(value = '') {
  return String(value).replace(/[&<>"']/g, character => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&apos;'
  })[character]);
}

function wrapText(value, maxCharacters = 30, maxLines = 4) {
  const words = String(value).trim().split(/\s+/);
  const lines = [];
  let current = '';
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > maxCharacters && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines.slice(0, maxLines);
}

function textBlock(lines, { x, y, size, lineHeight, fill = '#fff', weight = 800, anchor = 'middle' }) {
  return `<text x="${x}" y="${y}" fill="${fill}" text-anchor="${anchor}" font-family="Arial,Helvetica,sans-serif" font-size="${size}" font-weight="${weight}">${lines.map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : lineHeight}">${escapeXml(line)}</tspan>`).join('')}</text>`;
}

function backgroundSvg(setting, accent, phase) {
  const pulse = phase ? 0.15 : 0.08;
  const common = `
    <rect width="540" height="960" fill="#0A0D16"/>
    <circle cx="95" cy="180" r="180" fill="${accent}" opacity="${pulse}"/>
    <circle cx="490" cy="600" r="240" fill="#6D28D9" opacity="0.09"/>
    <rect y="655" width="540" height="305" fill="#070910"/>
    <path d="M0 655H540" stroke="#667085" stroke-width="3" opacity="0.35"/>`;

  const backgrounds = {
    hallway: `<rect x="35" y="180" width="470" height="475" rx="8" fill="#252A38"/><path d="M270 180V655M35 420H505" stroke="#3D4354" stroke-width="5"/><rect x="210" y="255" width="120" height="400" rx="5" fill="#121722" stroke="#677189" stroke-width="5"/><circle cx="305" cy="455" r="7" fill="#F9C74F"/>`,
    kitchen: `<rect x="30" y="215" width="480" height="440" rx="10" fill="#24313A"/><rect x="50" y="470" width="440" height="175" fill="#151E25"/><rect x="70" y="285" width="125" height="335" rx="8" fill="#B8C2CA"/><rect x="82" y="305" width="101" height="145" rx="4" fill="#8B969E"/><path d="M208 500H470V635H208Z" fill="#2E4950"/>`,
    apartment: `<rect x="25" y="200" width="490" height="455" rx="10" fill="#23293A"/><rect x="55" y="280" width="210" height="170" fill="#101827" stroke="#465166" stroke-width="8"/><path d="M60 455H300V625H60Z" fill="#31394B"/><rect x="330" y="255" width="145" height="370" fill="#151A26"/>`,
    laundromat: `<rect x="25" y="190" width="490" height="465" rx="10" fill="#23313B"/>${[65,195,325].map(x => `<rect x="${x}" y="275" width="115" height="250" rx="12" fill="#CBD3DA"/><circle cx="${x+57}" cy="370" r="42" fill="#27384A" stroke="#6E8398" stroke-width="7"/>`).join('')}<path d="M45 565H495" stroke="#B9C5CE" stroke-width="16"/>`,
    elevator: `<rect x="35" y="175" width="470" height="480" fill="#303643"/><path d="M270 180V650" stroke="#798293" stroke-width="7"/><rect x="455" y="265" width="28" height="95" rx="6" fill="#10131A"/><circle cx="469" cy="292" r="7" fill="#FF4D6D"/><circle cx="469" cy="331" r="7" fill="#F9C74F"/>`,
    lobby: `<rect x="20" y="180" width="500" height="475" fill="#1F2B35"/><rect x="55" y="255" width="185" height="135" fill="#0A1420" stroke="#566575" stroke-width="7"/><rect x="315" y="245" width="150" height="260" fill="#263B45"/><circle cx="390" cy="315" r="48" fill="#111827" stroke="#E5E7EB" stroke-width="5"/><path d="M390 315V280M390 315L420 335" stroke="#fff" stroke-width="5"/>`,
    bus: `<rect x="20" y="185" width="500" height="470" rx="22" fill="#202A39"/><rect x="50" y="230" width="440" height="210" rx="12" fill="#061726"/><path d="M195 230V440M345 230V440" stroke="#4C5E72" stroke-width="7"/><path d="M45 560H495" stroke="#8C98A8" stroke-width="8"/><path d="M110 500V630M430 500V630" stroke="#39465A" stroke-width="22"/>`,
    street: `<rect y="185" width="540" height="470" fill="#101D2A"/><path d="M0 585L540 535V655H0Z" fill="#242A35"/><rect x="45" y="280" width="145" height="280" fill="#263446"/><rect x="350" y="235" width="150" height="315" fill="#212F40"/>${[75,120,380,430].map(x=>`<rect x="${x}" y="320" width="24" height="45" fill="#F9C74F" opacity="0.55"/>`).join('')}`,
    shop: `<rect x="20" y="185" width="500" height="470" fill="#2A2422"/><path d="M40 295H500M40 425H500" stroke="#7A5B44" stroke-width="16"/>${[75,155,235,335,415].map((x,i)=>`<rect x="${x}" y="${i%2?330:250}" width="42" height="65" rx="5" fill="${i%2?'#B08968':'#7F5539'}"/>`).join('')}<rect x="60" y="515" width="420" height="125" fill="#4D382D"/>`,
    office: `<rect x="20" y="185" width="500" height="470" fill="#1F2937"/><rect x="45" y="230" width="205" height="165" fill="#0B1B2E" stroke="#546276" stroke-width="8"/><path d="M65 540H475" stroke="#7B8797" stroke-width="26"/><rect x="155" y="455" width="125" height="80" rx="8" fill="#0E1726"/>`,
    garage: `<rect x="20" y="180" width="500" height="475" fill="#242A32"/><path d="M25 285H515M25 500H515" stroke="#4A5260" stroke-width="7"/><path d="M95 185V655M445 185V655" stroke="#313945" stroke-width="18"/><path d="M125 540Q270 450 415 540L455 620H85Z" fill="#111722" stroke="#596478" stroke-width="6"/>`,
    cafe: `<rect x="20" y="185" width="500" height="470" fill="#302723"/><rect x="45" y="230" width="200" height="170" fill="#10212A" stroke="#826B5D" stroke-width="8"/><path d="M55 520H485" stroke="#8B6048" stroke-width="30"/><circle cx="395" cy="390" r="52" fill="#5B3A29"/><path d="M395 442V610" stroke="#5B3A29" stroke-width="20"/>`,
    motel: `<rect x="20" y="185" width="500" height="470" fill="#272437"/><rect x="65" y="245" width="165" height="360" fill="#161522"/><text x="148" y="330" fill="#F9C74F" text-anchor="middle" font-size="46" font-family="Arial" font-weight="900">404</text><rect x="315" y="300" width="150" height="110" fill="#0A1524" stroke="#575068" stroke-width="7"/>`,
    bedroom: `<rect x="20" y="185" width="500" height="470" fill="#2A2738"/><rect x="55" y="250" width="170" height="120" fill="#141B29" stroke="#665F79" stroke-width="7"/><path d="M65 505H355V635H65Z" fill="#4B4562"/><rect x="355" y="245" width="120" height="380" fill="#16141F"/>`,
    park: `<rect y="180" width="540" height="475" fill="#132D2A"/><circle cx="90" cy="300" r="115" fill="#1E5948"/><circle cx="455" cy="330" r="140" fill="#1C4B3F"/><path d="M95 350V655M450 390V655" stroke="#5B3A29" stroke-width="34"/><path d="M0 610Q270 540 540 610V655H0Z" fill="#263E35"/>
      <ellipse cx="275" cy="590" rx="42" ry="25" fill="#F4D35E"/><circle cx="310" cy="575" r="21" fill="#F4D35E"/><path d="M330 578L352 587L330 592Z" fill="#F97316"/><circle cx="315" cy="570" r="3" fill="#111"/><rect x="290" y="545" width="35" height="18" rx="4" fill="#4B5563"/><circle cx="307" cy="546" r="10" fill="#F9C74F"/>`
  };

  return common + (backgrounds[setting] || backgrounds.hallway);
}

function poseFor(action, active, phase) {
  if (!active) return { left:-12, right:12, lean:0, step:0 };
  const swing = phase ? 1 : -1;
  const poses = {
    point:{ left:-18, right:-72, lean:-2, step:0 },
    reach:{ left:-22, right:-62, lean:-4, step:0 },
    knock:{ left:-15, right:-78 + phase * 12, lean:-5, step:0 },
    'open-door':{ left:-20, right:-66, lean:-6, step:phase * 5 },
    'slam-door':{ left:55, right:-62, lean:-8, step:phase * 7 },
    phone:{ left:-12, right:-48, lean:0, step:0 },
    run:{ left:42 * swing, right:-42 * swing, lean:8, step:12 * swing },
    'step-back':{ left:-25, right:25, lean:phase ? -7 : 2, step:-phase * 8 },
    freeze:{ left:-35, right:35, lean:0, step:0 },
    'hand-object':{ left:-18, right:-58, lean:-2, step:0 },
    pull:{ left:54, right:-54, lean:phase ? 8 : 3, step:0 },
    gesture:{ left:-55, right:55, lean:0, step:0 },
    laugh:{ left:-46, right:46, lean:phase ? 5 : -3, step:0 },
    handshake:{ left:-15, right:-65, lean:-2, step:4 },
    hide:{ left:-18, right:18, lean:phase ? -9 : -2, step:-8 },
    turn:{ left:-12, right:12, lean:phase ? 7 : -7, step:0 },
    look:{ left:-10, right:10, lean:phase ? 4 : -2, step:0 },
    walk:{ left:30 * swing, right:-30 * swing, lean:3, step:9 * swing },
    wave:{ left:-12, right:-75 + phase * 14, lean:0, step:0 }
  };
  return poses[action] || poses.gesture;
}

function characterSvg(character, x, y, { active, action, speaking, phase, mirror = false }) {
  const pose = poseFor(action, active, phase);
  const direction = mirror ? -1 : 1;
  const mouth = speaking
    ? `<ellipse cx="0" cy="-116" rx="10" ry="${phase ? 9 : 6}" fill="#321519"/><path d="M-6 -118Q0 -113 6 -118" stroke="#fff" stroke-width="2" fill="none" opacity="0.75"/>`
    : `<path d="M-9 -116Q0 -111 9 -116" stroke="#321519" stroke-width="4" fill="none" stroke-linecap="round"/>`;
  const eyeShift = active ? direction * 2 : 0;
  const phone = active && action === 'phone' ? `<rect x="${direction * 49 - 9}" y="-150" width="18" height="36" rx="4" fill="#0B1020" stroke="#8BE9FD" stroke-width="3"/>` : '';
  const object = active && action === 'hand-object' ? `<rect x="${direction * 57 - 13}" y="-72" width="26" height="34" rx="4" fill="#F9C74F" stroke="#fff" stroke-width="2"/>` : '';

  return `<g transform="translate(${x + pose.step * direction} ${y}) rotate(${pose.lean * direction})" opacity="${active ? 1 : 0.76}">
    <ellipse cx="0" cy="24" rx="56" ry="13" fill="#000" opacity="0.28"/>
    <path d="M-22 -8L-28 58M22 -8L30 58" stroke="${character.pants}" stroke-width="22" stroke-linecap="round"/>
    <path d="M-31 -80Q0 -98 31 -80L35 -5Q0 16 -35 -5Z" fill="${character.shirt}" stroke="#ffffff" stroke-opacity="0.13" stroke-width="4"/>
    <path d="M-27 -70L${pose.left * direction} -25" stroke="${character.skin}" stroke-width="17" stroke-linecap="round"/>
    <path d="M27 -70L${pose.right * direction} -25" stroke="${character.skin}" stroke-width="17" stroke-linecap="round"/>
    ${phone}${object}
    <rect x="-12" y="-101" width="24" height="27" rx="8" fill="${character.skin}"/>
    <ellipse cx="0" cy="-140" rx="43" ry="51" fill="${character.skin}" stroke="#000" stroke-opacity="0.18" stroke-width="4"/>
    <path d="M-42 -148Q-30 -204 14 -192Q48 -184 42 -145Q20 -170 -10 -166Q-27 -163 -42 -148Z" fill="${character.hair}"/>
    <ellipse cx="${-14 + eyeShift}" cy="-142" rx="4" ry="5" fill="#111"/><ellipse cx="${14 + eyeShift}" cy="-142" rx="4" ry="5" fill="#111"/>
    <path d="M-22 -155Q-14 -161 -6 -155M6 -155Q14 -161 22 -155" stroke="${character.hair}" stroke-width="4" fill="none" stroke-linecap="round"/>
    ${mouth}
  </g>`;
}

function sceneSvg(story, sceneItem, sceneIndex, { mouthOpen, phase }) {
  const accent = sceneItem.mood === 'funny' ? '#F9C74F' : ['#8B5CF6','#00BBF9','#F15BB5','#00D4A8'][sceneIndex % 4];
  const speaker = story.characters.find(character => character.id === sceneItem.speaker) || story.characters[0];
  const other = story.characters.find(character => character.id !== speaker.id) || story.characters[1];
  const speakerLeft = speaker.id === 'A';
  const captionLines = wrapText(sceneItem.dialogue, 36, 4);
  const titleLines = wrapText(story.title.toUpperCase(), 22, 2);
  const progress = Math.round(((sceneIndex + 1) / story.scenes.length) * 490);

  return `<svg width="${WIDTH}" height="${HEIGHT}" viewBox="0 0 ${WIDTH} ${HEIGHT}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="caption" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#111827" stop-opacity="0.84"/><stop offset="1" stop-color="#02040A" stop-opacity="0.97"/></linearGradient>
      <filter id="shadow"><feDropShadow dx="0" dy="6" stdDeviation="9" flood-opacity="0.55"/></filter>
    </defs>
    ${backgroundSvg(sceneItem.setting, accent, phase)}
    <rect x="16" y="20" width="508" height="130" rx="20" fill="#05060A" opacity="0.72" filter="url(#shadow)"/>
    <text x="270" y="52" fill="#fff" opacity="0.75" text-anchor="middle" font-family="Arial" font-size="17" font-weight="700" letter-spacing="4">RUBY'S REALM</text>
    ${textBlock(titleLines,{x:270,y:88,size:28,lineHeight:31,fill:accent,weight:900})}
    ${characterSvg(speakerLeft ? speaker : other, 150, 630, {active:speakerLeft,action:sceneItem.action,speaking:speakerLeft && mouthOpen,phase,mirror:false})}
    ${characterSvg(speakerLeft ? other : speaker, 390, 630, {active:!speakerLeft,action:sceneItem.action,speaking:!speakerLeft && mouthOpen,phase,mirror:true})}
    <rect x="18" y="704" width="504" height="218" rx="24" fill="url(#caption)" stroke="${accent}" stroke-opacity="0.55" stroke-width="3"/>
    <text x="42" y="742" fill="${accent}" font-family="Arial" font-size="20" font-weight="900">${escapeXml(speaker.name.toUpperCase())}</text>
    ${textBlock(captionLines,{x:270,y:782,size:29,lineHeight:36,fill:'#fff',weight:900})}
    <rect x="25" y="936" width="490" height="7" rx="4" fill="#fff" opacity="0.16"/><rect x="25" y="936" width="${progress}" height="7" rx="4" fill="${accent}"/>
  </svg>`;
}

function run(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(FFMPEG, args, { stdio:['ignore','ignore','pipe'] });
    let stderr = '';
    child.stderr.on('data', chunk => { stderr += chunk.toString(); });
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve() : reject(new Error(`ffmpeg ${code}: ${stderr.slice(-2200)}`)));
  });
}

async function mapLimit(items, limit, worker) {
  const results = new Array(items.length);
  let cursor = 0;
  async function consume() {
    while (cursor < items.length) {
      const index = cursor++;
      results[index] = await worker(items[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, consume));
  return results;
}

function wavDuration(buffer) {
  if (buffer.length < 44 || buffer.toString('ascii', 0, 4) !== 'RIFF') return 0;
  const byteRate = buffer.readUInt32LE(28);
  let offset = 12;
  while (offset + 8 <= buffer.length) {
    const chunkId = buffer.toString('ascii', offset, offset + 4);
    const size = buffer.readUInt32LE(offset + 4);
    if (chunkId === 'data') return byteRate ? size / byteRate : 0;
    offset += 8 + size + (size % 2);
  }
  return 0;
}

async function fliteFallback(text, voice, output, dir, index) {
  const textFile = path.join(dir, `speech-${index}.txt`);
  await fs.writeFile(textFile, String(text).replace(/\s+/g, ' ').trim());
  const fliteVoice = { onyx:'rms', echo:'awb', nova:'slt', shimmer:'slt', alloy:'kal' }[voice] || 'kal';
  await run([
    '-y','-f','lavfi','-i',`flite=textfile=${textFile}:voice=${fliteVoice}`,
    '-ar','24000','-ac','1','-c:a','pcm_s16le',output
  ]);
}

async function speechFile(sceneItem, character, dir, index) {
  const raw = path.join(dir, `speech-${index}.raw`);
  const output = path.join(dir, `speech-${index}.wav`);
  let provider = 'gateway';

  try {
    const audio = await generateSpeechAudio({ text:sceneItem.dialogue, voice:character.voice });
    await fs.writeFile(raw, audio);
    await run(['-y','-i',raw,'-ar','24000','-ac','1','-c:a','pcm_s16le',output]);
  } catch (error) {
    provider = 'flite-fallback';
    console.warn(`Speech generation failed for scene ${index + 1}; using local fallback`, error.message);
    await fliteFallback(sceneItem.dialogue, character.voice, output, dir, index);
  }

  const buffer = await fs.readFile(output);
  const duration = wavDuration(buffer);
  if (!duration || duration > 40) throw new Error(`Invalid speech duration for scene ${index + 1}.`);
  return { path:output, duration, provider };
}

function quoteConcatPath(file) {
  return file.replaceAll("'", "'\\''");
}

async function renderStory(story, dir) {
  const speech = await mapLimit(story.scenes, 3, async (sceneItem, index) => {
    const character = story.characters.find(item => item.id === sceneItem.speaker) || story.characters[0];
    return speechFile(sceneItem, character, dir, index);
  });

  const frameFiles = [];
  for (let sceneIndex = 0; sceneIndex < story.scenes.length; sceneIndex++) {
    const variants = {};
    for (const phase of [0,1]) {
      for (const mouth of [0,1]) {
        const file = path.join(dir, `scene-${sceneIndex}-${phase}-${mouth}.png`);
        const svg = sceneSvg(story, story.scenes[sceneIndex], sceneIndex, { mouthOpen:Boolean(mouth), phase });
        await sharp(Buffer.from(svg)).png({ compressionLevel:5 }).toFile(file);
        variants[`${phase}-${mouth}`] = file;
      }
    }
    frameFiles.push(variants);
  }

  const silence = path.join(dir, 'silence.wav');
  await run(['-y','-f','lavfi','-i','anullsrc=r=24000:cl=mono','-t',String(SCENE_GAP),'-c:a','pcm_s16le',silence]);

  const audioConcat = [];
  const videoConcat = [];
  let totalDuration = 0;

  for (let sceneIndex = 0; sceneIndex < story.scenes.length; sceneIndex++) {
    const spokenDuration = speech[sceneIndex].duration;
    const frames = frameFiles[sceneIndex];
    audioConcat.push(`file '${quoteConcatPath(speech[sceneIndex].path)}'`);
    audioConcat.push(`file '${quoteConcatPath(silence)}'`);

    let elapsed = 0;
    let frameNumber = 0;
    while (elapsed < spokenDuration) {
      const step = Math.min(MOUTH_STEP, spokenDuration - elapsed);
      const phase = elapsed >= spokenDuration / 2 ? 1 : 0;
      const mouth = frameNumber % 3 === 0 ? 0 : 1;
      videoConcat.push(`file '${quoteConcatPath(frames[`${phase}-${mouth}`])}'`);
      videoConcat.push(`duration ${step.toFixed(6)}`);
      elapsed += step;
      frameNumber++;
    }
    videoConcat.push(`file '${quoteConcatPath(frames['1-0'])}'`);
    videoConcat.push(`duration ${SCENE_GAP.toFixed(6)}`);
    totalDuration += spokenDuration + SCENE_GAP;
  }

  const lastFrame = frameFiles[frameFiles.length - 1]['1-0'];
  videoConcat.push(`file '${quoteConcatPath(lastFrame)}'`);

  const audioList = path.join(dir, 'audio-concat.txt');
  const videoList = path.join(dir, 'video-concat.txt');
  const voiceTrack = path.join(dir, 'voice.wav');
  const output = path.join(dir, 'story.mp4');
  await fs.writeFile(audioList, audioConcat.join('\n'));
  await fs.writeFile(videoList, videoConcat.join('\n'));

  await run(['-y','-f','concat','-safe','0','-i',audioList,'-ar','24000','-ac','1','-c:a','pcm_s16le',voiceTrack]);
  const fadeOut = Math.max(0, totalDuration - 1.2).toFixed(2);
  await run([
    '-y',
    '-f','concat','-safe','0','-i',videoList,
    '-i',voiceTrack,
    '-f','lavfi','-i',`sine=frequency=82:sample_rate=44100:duration=${totalDuration.toFixed(3)}`,
    '-f','lavfi','-i',`anoisesrc=color=pink:amplitude=0.25:sample_rate=44100:duration=${totalDuration.toFixed(3)}`,
    '-filter_complex',`[1:a]volume=1.0[voice];[2:a]volume=0.025,lowpass=f=900[tone];[3:a]volume=0.012,highpass=f=80,lowpass=f=1600[air];[voice][tone][air]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.92,afade=t=in:st=0:d=0.25,afade=t=out:st=${fadeOut}:d=1.2[aout]`,
    '-map','0:v:0','-map','[aout]',
    '-vf',`scale=${WIDTH}:${HEIGHT}:flags=fast_bilinear,format=yuv420p`,
    '-r',String(FPS),'-t',totalDuration.toFixed(3),'-shortest',
    '-c:v','libx264','-preset','ultrafast','-crf','28','-pix_fmt','yuv420p',
    '-c:a','aac','-b:a','128k','-ar','44100','-ac','2',
    '-movflags','+faststart',output
  ]);

  return {
    output,
    duration:totalDuration,
    speechProviders:[...new Set(speech.map(item => item.provider))]
  };
}

function responseHeaders(res, seed) {
  res.setHeader('Content-Type','video/mp4');
  res.setHeader('Cache-Control','public, max-age=31536000, s-maxage=31536000, immutable');
  res.setHeader('X-Rubys-Realm-Format','animated-story-v2');
  res.setHeader('X-Rubys-Realm-Branding','brand-only');
  res.setHeader('X-Rubys-Realm-Seed',seed);
  res.setHeader('X-AI-Generated','true');
}

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') return res.status(405).end();
  const rawSeed = String(req.query?.seed || new Date().toISOString().slice(0,10));
  const seed = rawSeed.replace(/[^a-zA-Z0-9_-]/g,'').slice(0,80) || 'rubys-realm';
  const long = String(req.query?.long || '') === '1';
  responseHeaders(res, seed);

  if (req.method === 'HEAD') return res.status(200).end();

  const dir = await fs.mkdtemp(path.join(os.tmpdir(), `rr-story-${seed}-`));
  try {
    const story = await createStory(seed, { long });
    const rendered = await renderStory(story, dir);
    const video = await fs.readFile(rendered.output);
    res.setHeader('Content-Length',String(video.length));
    res.setHeader('X-Rubys-Realm-Duration',rendered.duration.toFixed(2));
    res.setHeader('X-Rubys-Realm-Voices',rendered.speechProviders.join(','));
    return res.status(200).send(video);
  } catch (error) {
    console.error('animated story render failed', error);
    return res.status(500).json({ ok:false, error:'Animated story render failed', detail:error.message });
  } finally {
    await fs.rm(dir,{ recursive:true,force:true }).catch(()=>{});
  }
}
