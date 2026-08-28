import { generateStoryJson, hasGatewayAuth } from '../lib/ai-gateway.js';

const CHARACTER_PAIRS = [
  [
    { id:'A', name:'Marcus', voice:'onyx', skin:'#8B5E3C', hair:'#161616', shirt:'#5B5FEF', pants:'#20283A' },
    { id:'B', name:'Nia', voice:'nova', skin:'#6E432D', hair:'#25150F', shirt:'#E94F8A', pants:'#252B3D' }
  ],
  [
    { id:'A', name:'Eli', voice:'echo', skin:'#C98F68', hair:'#3A2419', shirt:'#008E9B', pants:'#263247' },
    { id:'B', name:'Tessa', voice:'shimmer', skin:'#D9A37C', hair:'#6D2E1C', shirt:'#8A5CF6', pants:'#2D3144' }
  ],
  [
    { id:'A', name:'Andre', voice:'onyx', skin:'#70452E', hair:'#121212', shirt:'#D97706', pants:'#20283A' },
    { id:'B', name:'Maya', voice:'nova', skin:'#A86F4B', hair:'#1A1210', shirt:'#16A085', pants:'#293044' }
  ],
  [
    { id:'A', name:'Caleb', voice:'echo', skin:'#E0AD86', hair:'#4B2F21', shirt:'#2563EB', pants:'#252B3D' },
    { id:'B', name:'Renee', voice:'shimmer', skin:'#7D4E35', hair:'#20140F', shirt:'#DB2777', pants:'#283248' }
  ]
];

const SAFE_ACTIONS = new Set(['point','step-back','reach','knock','open-door','slam-door','look','turn','phone','run','freeze','hand-object','pull','gesture','laugh','handshake','hide','walk','wave']);
const SAFE_SETTINGS = new Set(['hallway','kitchen','apartment','laundromat','elevator','lobby','bus','street','shop','office','garage','cafe','motel','bedroom','park']);
const DAILY_DURATION_MINUTES = [2.5, 3.25, 4.25, 5.25, 6.75, 8.5];
const TARGET_WORDS_PER_SCENE = 19;

const PLOTS = [
  {
    genre:'horror', title:'The Elevator Found Floor Zero', settings:['elevator','lobby','hallway'],
    inciting:'the elevator has a glowing floor-zero button that was never there before',
    clue:'two visitor badges are waiting downstairs with our names and tomorrow’s date',
    danger:'a knocking sound follows the elevator and matches every floor we pass',
    consequence:'the building above us begins disappearing from the security monitors one floor at a time',
    twist:'floor zero is not underground; it is a copy of the building trying to replace the original',
    finale:'the elevator opens upstairs again, but one of our reflections steps out before either of us moves'
  },
  {
    genre:'comedy', title:'My Refrigerator Sued Me', settings:['kitchen','apartment','hallway'],
    inciting:'a tiny attorney has arrived to represent the refrigerator in a lawsuit against me',
    clue:'the evidence includes weeks of footage showing me opening the door with no actual snack plan',
    danger:'the freezer has hired separate counsel and the microwave is recording every word we say',
    consequence:'every appliance in the apartment joins the case and starts demanding weekends, breaks, and back pay',
    twist:'the refrigerator does not want money; it wants legal ownership of every leftover after midnight',
    finale:'we settle the case, then the coffee maker slides a brand-new lawsuit across the counter'
  },
  {
    genre:'thriller', title:'Tomorrow Called Twice', settings:['apartment','hallway','street'],
    inciting:'my phone is calling from tomorrow even though the phone itself is sitting in my hand',
    clue:'the voice predicts each blackout and tells us which hallway camera will fail next',
    danger:'the caller begins counting down to something that happens every time the number reaches zero',
    consequence:'security footage shows us leaving the building tomorrow while we are still standing inside tonight',
    twist:'the future caller is not warning us about the building; it is warning us about the versions of us outside',
    finale:'the call ends, then both of our phones ring from the exact same number at the exact same time'
  },
  {
    genre:'mystery', title:'The Store That Sold My Memory', settings:['shop','street','apartment'],
    inciting:'a receipt says I sold a childhood memory here ten minutes from now',
    clue:'the clerk has an object from my childhood that nobody outside my family should recognize',
    danger:'each minute inside the store removes another detail from why we came here in the first place',
    consequence:'a second version of me appears outside holding the same receipt and begging us not to finish the sale',
    twist:'one of us is not a customer at all; one of us is the memory listed as merchandise',
    finale:'the store closes and only one of us remembers ever knowing the other'
  },
  {
    genre:'comedy-thriller', title:'My Replacement Arrived Early', settings:['office','elevator','hallway'],
    inciting:'an exact copy of me is already at my desk finishing work I have avoided for three weeks',
    clue:'management has records proving the copy has worked here longer than I have',
    danger:'more copies keep arriving from the elevator and every one remembers a different version of my life',
    consequence:'the building locks down while human resources tries to decide which employee is legally original',
    twist:'the first copy claims the real me escaped months ago and everyone still working here is a replacement',
    finale:'the doors finally unlock, but the name on my badge changes before I can leave'
  },
  {
    genre:'horror', title:'My Shadow Parked First', settings:['garage','street','hallway'],
    inciting:'my shadow is standing beside the car while I am still several steps away from it',
    clue:'the shadow is holding keys that are physically still in your hand',
    danger:'every time a garage light flickers, both shadows move closer to the driver and passenger doors',
    consequence:'the dashboard counts two passengers inside even though the real car is visibly empty',
    twist:'the shadows are not copying us anymore; they are rehearsing what they plan to do after leaving',
    finale:'the garage lights return and our shadows are normal again, except the car is suddenly gone'
  },
  {
    genre:'mystery', title:'The Dryer Returned Tomorrow', settings:['laundromat','street','apartment'],
    inciting:'a dryer contains clothes we are both still wearing right now',
    clue:'a receipt in the pocket is dated tomorrow and carries a warning in my handwriting',
    danger:'every washer starts counting down together even though nobody touched their controls',
    consequence:'the front windows show an empty laundromat while we can still see ourselves trapped inside',
    twist:'the machines are not showing the future; they are swapping objects between two versions of tonight',
    finale:'the doors finally open and we step outside carrying one jacket that neither of us remembers owning'
  },
  {
    genre:'thriller', title:'The Bus Stop After the Last Stop', settings:['bus','street','apartment'],
    inciting:'the bus has passed our stop three times and keeps returning to the same empty street',
    clue:'the route display has erased every destination and now shows only our two names',
    danger:'each time we pull the stop cord, another passenger silently disappears',
    consequence:'the driver says one of us can leave but the other must finish the route',
    twist:'every house outside belongs to someone who once disappeared from this bus',
    finale:'the doors open at my childhood home and somebody with your face is already waiting on the porch'
  },
  {
    genre:'horror', title:'Room 404 Was My Bedroom', settings:['motel','bedroom','hallway'],
    inciting:'a motel key marked 404 opens a room identical to my childhood bedroom',
    clue:'every photograph on the wall includes you even though we did not meet until years later',
    danger:'the hallway outside grows longer every time we try to leave',
    consequence:'the room begins changing to match memories I have never told anyone about',
    twist:'the motel is not recreating my past; it is testing which memories belong to the person who entered',
    finale:'we escape to the parking lot and find room 404 reflected in every dark window around us'
  },
  {
    genre:'comedy-mystery', title:'The Duck Detective Hired Me', settings:['park','street','cafe'],
    inciting:'a duck wearing a tiny detective hat has dropped a case file at my feet',
    clue:'the file contains photographs of our lunch disappearing before we even bought it',
    danger:'every pigeon in the park starts following us like an organized surveillance team',
    consequence:'the duck leads us through clues pointing to a snack-smuggling operation under the café patio',
    twist:'the missing food was never stolen; the detective has been planting evidence to keep himself employed',
    finale:'we expose the scheme and the duck immediately hands us a bill for professional investigative services'
  }
];

const ACTION_CYCLE = ['point','look','gesture','step-back','phone','reach','walk','turn','hand-object','freeze','run','open-door'];
const END_PHRASES = [
  'Stay with me, because this is getting worse.',
  'Do not touch anything until we know why.',
  'Keep watching; something changed again.',
  'Tell me you noticed that too.',
  'We need to think before we move.',
  'Whatever happens, do not split up.',
  'That detail was not there a minute ago.',
  'I am starting to understand what this wants.'
];

function hashSeed(value) {
  let hash = 2166136261;
  for (const character of String(value)) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function pick(list, seed, offset = 0) {
  return list[((seed + Math.imul(offset + 1, 2654435761)) >>> 0) % list.length];
}

function words(value) {
  return String(value).trim().split(/\s+/).filter(Boolean);
}

function fitDialogue(value, seed, index) {
  let parts = words(value);
  if (parts.length > 23) parts = parts.slice(0, 23);
  let text = parts.join(' ');
  let guard = 0;
  while (words(text).length < 17 && guard < 4) {
    text += ` ${pick(END_PHRASES, seed, index + guard)}`;
    guard++;
  }
  parts = words(text);
  if (parts.length > 23) parts = parts.slice(0, 23);
  text = parts.join(' ');
  if (!/[.!?]$/.test(text)) text += '.';
  return text;
}

function durationForSeed(seedValue) {
  const slotMatch = String(seedValue).match(/^(.*)-slot-(\d+)$/);
  if (slotMatch) {
    const dayRotation = hashSeed(`${slotMatch[1]}:duration`) % DAILY_DURATION_MINUTES.length;
    const slot = Math.max(0, Number(slotMatch[2]) - 1);
    return DAILY_DURATION_MINUTES[(slot + dayRotation) % DAILY_DURATION_MINUTES.length];
  }
  return DAILY_DURATION_MINUTES[hashSeed(`${seedValue}:duration`) % DAILY_DURATION_MINUTES.length];
}

function phaseFor(index, count) {
  const progress = count <= 1 ? 1 : index / (count - 1);
  if (progress < 0.12) return 'hook';
  if (progress < 0.28) return 'investigate';
  if (progress < 0.48) return 'escalate';
  if (progress < 0.66) return 'consequence';
  if (progress < 0.82) return 'twist';
  if (progress < 0.95) return 'climax';
  return 'finale';
}

function lineForPhase(plot, phase, speakerName, otherName, seed, index) {
  const variants = {
    hook: [
      `${otherName}, I need you to look at this carefully: ${plot.inciting}.`,
      `I thought I imagined it, ${otherName}, but ${plot.inciting}.`,
      `${otherName}, this started like a normal night, then ${plot.inciting}.`,
      `Before we do anything else, explain why ${plot.inciting}.`
    ],
    investigate: [
      `Look closer, ${otherName}. ${plot.clue}, and that cannot be an accident.`,
      `I checked twice, ${otherName}. ${plot.clue}, which means somebody expected us here.`,
      `${otherName}, the strangest part is this: ${plot.clue}.`,
      `That gives us our first real clue, ${otherName}: ${plot.clue}.`
    ],
    escalate: [
      `${otherName}, stop for a second. ${plot.danger}, and it is happening faster now.`,
      `This is not random anymore, ${otherName}. ${plot.danger}, exactly when we move.`,
      `I was hoping this would calm down, but ${plot.danger}.`,
      `${otherName}, whatever started this is reacting to us because ${plot.danger}.`
    ],
    consequence: [
      `We waited too long, ${otherName}. ${plot.consequence}, so our choices are getting smaller.`,
      `${otherName}, this just became serious: ${plot.consequence}.`,
      `Every clue points the same direction now. ${plot.consequence}, and we are running out of room.`,
      `I think our last decision triggered it, ${otherName}. ${plot.consequence}.`
    ],
    twist: [
      `${otherName}, I finally see the pattern. ${plot.twist}, which changes everything we thought we knew.`,
      `Wait, ${otherName}. The clues only make sense if ${plot.twist}.`,
      `I was looking at this backward. ${plot.twist}, and that means the danger is much closer.`,
      `${otherName}, the answer was in front of us the whole time: ${plot.twist}.`
    ],
    climax: [
      `Then we act now, ${otherName}. We use what we learned, stay together, and force this thing to reveal itself.`,
      `${otherName}, no more waiting. We know the pattern now, so we move before it gets another chance.`,
      `I have one plan left, ${otherName}. It is risky, but doing nothing is exactly what this expects.`,
      `${otherName}, follow my lead. If the pattern repeats once more, we use that moment to break it.`
    ],
    finale: [
      `${otherName}, we almost made it, but ${plot.finale}.`,
      `I thought it was over, ${otherName}. Then ${plot.finale}.`,
      `${otherName}, remember everything we just learned, because ${plot.finale}.`,
      `We got our answer, ${otherName}, and I wish we had not: ${plot.finale}.`
    ]
  };
  return pick(variants[phase], seed, index);
}

function proceduralStory(seedValue) {
  const seed = hashSeed(seedValue);
  const pair = CHARACTER_PAIRS[seed % CHARACTER_PAIRS.length].map(character => ({ ...character }));
  const slotMatch = String(seedValue).match(/^(.*)-slot-(\d+)$/);
  const plotIndex = slotMatch
    ? (hashSeed(slotMatch[1]) + Math.max(0, Number(slotMatch[2]) - 1)) % PLOTS.length
    : (seed >>> 3) % PLOTS.length;
  const plot = PLOTS[plotIndex];
  const targetMinutes = durationForSeed(seedValue);
  const sceneCount = Math.max(16, Math.round(targetMinutes * 7.2));
  const scenes = [];

  for (let index = 0; index < sceneCount; index++) {
    const speaker = index % 2 === 0 ? pair[0] : pair[1];
    const other = index % 2 === 0 ? pair[1] : pair[0];
    const phase = phaseFor(index, sceneCount);
    const dialogue = fitDialogue(lineForPhase(plot, phase, speaker.name, other.name, seed, index), seed, index);
    const phasePosition = index / Math.max(1, sceneCount - 1);
    const settingIndex = Math.min(plot.settings.length - 1, Math.floor(phasePosition * plot.settings.length));
    scenes.push({
      speaker:speaker.id,
      dialogue,
      action:pick(ACTION_CYCLE, seed, index),
      setting:plot.settings[settingIndex],
      mood:plot.genre.includes('comedy') ? 'funny' : 'tense'
    });
  }

  const spokenWords = scenes.reduce((sum, item) => sum + words(item.dialogue).length, 0);
  return {
    id:`${plotIndex}-${seedValue}`,
    title:plot.title,
    genre:plot.genre,
    characters:pair,
    scenes,
    targetMinutes,
    targetSeconds:Math.round(targetMinutes * 60),
    spokenWords,
    sceneCount,
    durationRange:'2-9 minutes',
    caption:`${plot.title}. Full animated ${plot.genre.replaceAll('-',' ')} story with talking characters. Watch to the end. #RubysRealm #AnimatedStory #StoryTok #AIGenerated`
  };
}

function normalizeGeneratedStory(generated, base) {
  if (!generated || typeof generated !== 'object') throw new Error('Generated story is not an object.');
  if (!Array.isArray(generated.scenes) || generated.scenes.length < Math.floor(base.sceneCount * 0.8)) {
    throw new Error('Generated story did not contain enough scenes.');
  }

  const scenes = generated.scenes.slice(0, base.sceneCount).map((item, index) => {
    const speaker = item.speaker === 'B' ? 'B' : 'A';
    const dialogue = fitDialogue(String(item.dialogue || '').trim(), hashSeed(base.id), index);
    if (dialogue.length < 8) throw new Error(`Generated scene ${index + 1} has no dialogue.`);
    return {
      speaker,
      dialogue,
      action:SAFE_ACTIONS.has(item.action) ? item.action : base.scenes[index]?.action || 'gesture',
      setting:SAFE_SETTINGS.has(item.setting) ? item.setting : base.scenes[index]?.setting || 'hallway',
      mood:item.mood === 'funny' ? 'funny' : base.scenes[index]?.mood || 'tense'
    };
  });

  if (scenes.length < base.sceneCount) {
    scenes.push(...base.scenes.slice(scenes.length));
  }

  const spokenWords = scenes.reduce((sum, item) => sum + words(item.dialogue).length, 0);
  return {
    ...base,
    title:String(generated.title || base.title).trim().slice(0, 80),
    genre:String(generated.genre || base.genre).trim().slice(0, 30),
    scenes,
    spokenWords,
    caption:`${String(generated.title || base.title).trim().slice(0, 80)}. Full animated story with talking characters. Watch to the end. #RubysRealm #AnimatedStory #StoryTok #AIGenerated`
  };
}

async function aiStory(seedValue, base) {
  const [first, second] = base.characters;
  const approximateWords = base.sceneCount * TARGET_WORDS_PER_SCENE;
  const prompt = `Create one original ${base.genre} TikTok story inspired by the title "${base.title}".

Requirements:
- Exactly two visible ADULT characters: ${first.name} (speaker A) and ${second.name} (speaker B).
- Exactly ${base.sceneCount} chronological dialogue scenes.
- Target about ${approximateWords} total spoken words so the finished video lands near ${base.targetMinutes} minutes.
- Each scene should be roughly 17-23 spoken words.
- Build a complete beginning, escalation, investigation, twist, climax, and payoff or cliffhanger.
- Every scene must have one character speaking to the other. No narrator and no silent scenes.
- Characters must physically react and move throughout the story.
- Keep it PG-13: no gore, hate, sexual content, real-person impersonation, or copyrighted characters.
- action must be one of: ${[...SAFE_ACTIONS].join(', ')}.
- setting must be one of: ${[...SAFE_SETTINGS].join(', ')}.
- mood must be "tense" or "funny".
- Do not include hashtags, stage directions inside dialogue, or watermarks.
- Seed: ${seedValue}.

Return only JSON in this shape:
{"title":"...","genre":"...","scenes":[{"speaker":"A","dialogue":"...","action":"point","setting":"hallway","mood":"tense"}]}`;
  const generated = await generateStoryJson(prompt);
  return normalizeGeneratedStory(generated, base);
}

export async function createStory(seedValue, options = {}) {
  const base = proceduralStory(seedValue, options);
  if (!hasGatewayAuth() || process.env.AI_STORY_GENERATION === 'off') return base;
  try {
    return await aiStory(seedValue, base);
  } catch (error) {
    console.warn('AI story generation failed; using deterministic duration-driven story', error.message);
    return base;
  }
}

export function previewStory(seedValue, options = {}) {
  return proceduralStory(seedValue, options);
}
