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

function hashSeed(value) {
  let hash = 2166136261;
  for (const character of String(value)) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function pick(list, seed, offset = 0) {
  return list[(seed + offset * 2654435761 >>> 0) % list.length];
}

function scene(speaker, dialogue, action, setting, mood = 'tense') {
  return { speaker, dialogue, action, setting, mood };
}

const PLOTS = [
  {
    id:'door-knocked-back', genre:'mystery', title:'The Door That Knocked Back',
    build:({A,B,place,time}) => [
      scene('A',`${B}, was this door here when we came home? It has our apartment number on both sides.`,'point','hallway'),
      scene('B',`No. And do not touch it, ${A}. Nothing normal appears in a wall at ${time}.`,'step-back','hallway'),
      scene('A',`I only raised my hand. I never knocked, but something on the other side just did.`,'knock','hallway'),
      scene('B',`It knocked three times, exactly like you always do. Back away from that handle right now.`,'reach','hallway'),
      scene('A',`The handle is turning by itself. I can hear our refrigerator running behind the door.`,'open-door','hallway'),
      scene('B',`That is our kitchen in there, but look at the calendar. It says next Thursday.`,'point','kitchen'),
      scene('A',`There is someone sitting at our table. He looks like me, and he is holding this key.`,'look','kitchen'),
      scene('B',`He just mouthed, close it. ${A}, why is something knocking from behind us now?`,'turn','kitchen'),
      scene('A',`Because the first door was not trying to get in. It was trying to warn us.`,'slam-door','hallway')
    ]
  },
  {
    id:'tomorrow-call', genre:'thriller', title:'Tomorrow Called Twice',
    build:({A,B,time}) => [
      scene('B',`${A}, your phone keeps calling mine, but your phone is sitting right beside me.`,'phone','apartment'),
      scene('A',`The caller ID has tomorrow's date under my name. Put it on speaker, but say nothing.`,'reach','apartment'),
      scene('B',`It is your voice. You are whispering my name and counting backward from ten.`,'phone','apartment'),
      scene('A',`At zero, every light in this building just went out. That message knew it would happen.`,'look','apartment'),
      scene('B',`Wait. The voice says we have four minutes to leave, and we cannot use the front stairs.`,'point','apartment'),
      scene('A',`The hallway camera shows us already running outside. That recording is stamped ${time} tomorrow.`,'run','hallway'),
      scene('B',`Then why are the people in the recording stopping and looking straight at this camera?`,'freeze','hallway'),
      scene('A',`One of them is holding your phone. The call was never coming from my number.`,'step-back','hallway'),
      scene('B',`The countdown started again, ${A}. This time the voice sounds exactly like me.`,'run','hallway')
    ]
  },
  {
    id:'laundromat-loop', genre:'mystery', title:'The Dryer Returned Tomorrow',
    build:({A,B,object}) => [
      scene('A',`${B}, dryer seven stopped, but I never put our clothes inside that machine.`,'point','laundromat'),
      scene('B',`Then why is your ${object} spinning in there? You are wearing it right now.`,'reach','laundromat'),
      scene('A',`The pocket has a receipt dated tomorrow and a warning written in my handwriting.`,'hand-object','laundromat'),
      scene('B',`It says do not let the cycle finish. There are only forty seconds left.`,'phone','laundromat'),
      scene('A',`The door is locked. Every other machine just started counting down with it.`,'pull','laundromat'),
      scene('B',`Look through the glass. Those are not clothes anymore. That is this room, completely empty.`,'look','laundromat'),
      scene('A',`I can see us inside the drum. We are pounding on the glass from the other side.`,'step-back','laundromat'),
      scene('B',`The timer hit zero, but nothing opened. Why did the front door disappear?`,'turn','laundromat'),
      scene('A',`Because we were not watching the dryer. Someone outside was watching us.`,'freeze','laundromat')
    ]
  },
  {
    id:'room-zero', genre:'horror', title:'The Elevator Found Floor Zero',
    build:({A,B,place}) => [
      scene('B',`${A}, this elevator has never had a zero button. Why is it glowing now?`,'point','elevator'),
      scene('A',`I did not press it. The doors closed the second you said the word zero.`,'step-back','elevator'),
      scene('B',`The floor counter is going backward, but ${place} only has twelve floors above ground.`,'look','elevator'),
      scene('A',`Listen. Someone outside is matching the elevator, one knock for every floor we pass.`,'knock','elevator'),
      scene('B',`We stopped. The doors opened onto our lobby, except every clock is frozen at midnight.`,'open-door','lobby'),
      scene('A',`The security desk has two visitor badges waiting. They already have our names printed.`,'hand-object','lobby'),
      scene('B',`The guard in that photograph is pointing behind us. He was not moving a second ago.`,'turn','lobby'),
      scene('A',`Do not run to the elevator. Its display does not say zero anymore. It says occupied.`,'run','lobby'),
      scene('B',`Then we take the stairs. Unless that knocking is coming from inside them too.`,'freeze','lobby')
    ]
  },
  {
    id:'fridge-court', genre:'comedy', title:'My Refrigerator Sued Me',
    build:({A,B,object}) => [
      scene('A',`${B}, there is a tiny lawyer standing beside the refrigerator with a clipboard.`,'point','kitchen','funny'),
      scene('B',`He says the fridge is suing you for excessive opening without reasonable snack intent.`,'hand-object','kitchen','funny'),
      scene('A',`That is ridiculous. I always have snack intent, even when I forget what I wanted.`,'gesture','kitchen','funny'),
      scene('B',`Exhibit A is security footage of you staring inside for eleven minutes last Tuesday.`,'phone','kitchen','funny'),
      scene('A',`Objection. The cheese moved, and I was conducting a responsible investigation.`,'point','kitchen','funny'),
      scene('B',`The refrigerator demands weekends off, one new ${object}, and custody of the ice tray.`,'laugh','kitchen','funny'),
      scene('A',`Fine, but I want guaranteed access after midnight and no judgment about leftovers.`,'handshake','kitchen','funny'),
      scene('B',`The freezer rejected your offer. It has retained separate counsel and wants damages.`,'step-back','kitchen','funny'),
      scene('A',`Great. I lost a lawsuit to an appliance, and the microwave is recording everything.`,'look','kitchen','funny')
    ]
  },
  {
    id:'last-bus', genre:'thriller', title:'The Bus Stop After the Last Stop',
    build:({A,B,time}) => [
      scene('A',`${B}, the driver passed our stop three times, and the same street keeps coming back.`,'point','bus'),
      scene('B',`I asked him to stop. He said passengers who boarded after ${time} do not choose exits.`,'step-back','bus'),
      scene('A',`There were six people behind us earlier. Every seat is empty now except ours.`,'look','bus'),
      scene('B',`The route screen changed. It only shows two names, and they are ours.`,'phone','bus'),
      scene('A',`Pull the emergency cord. I do not care what the driver said.`,'reach','bus'),
      scene('B',`I pulled it. The sign says request accepted yesterday, but the doors are still locked.`,'pull','bus'),
      scene('A',`The bus finally stopped. That house outside is mine, but it burned down years ago.`,'freeze','street'),
      scene('B',`Someone is waiting on your porch. He has your jacket and my exact face.`,'point','street'),
      scene('A',`The driver says one of us can get off. The other has to finish the route.`,'step-back','bus')
    ]
  },
  {
    id:'memory-store', genre:'mystery', title:'The Store That Sold My Memory',
    build:({A,B,object}) => [
      scene('B',`${A}, this receipt says you bought a childhood memory here ten minutes from now.`,'hand-object','shop'),
      scene('A',`I have never seen this store, but that ${object} behind the counter belonged to my grandfather.`,'point','shop'),
      scene('B',`The clerk says you traded the memory willingly and asked him not to give it back.`,'look','shop'),
      scene('A',`Then why can I remember everything except the reason we came inside?`,'step-back','shop'),
      scene('B',`Because the receipt lists me as the item, not the customer. Read the bottom line.`,'hand-object','shop'),
      scene('A',`It says final sale at midnight. The clock just skipped forward twenty minutes.`,'phone','shop'),
      scene('B',`There is another version of you outside, pounding on the locked door.`,'point','shop'),
      scene('A',`He is shouting not to trust you, but he is holding the same receipt.`,'turn','shop'),
      scene('B',`Choose quickly. One of us is a memory, and the store is about to close.`,'reach','shop')
    ]
  },
  {
    id:'office-copy', genre:'comedy-thriller', title:'My Replacement Arrived Early',
    build:({A,B,place}) => [
      scene('A',`${B}, someone is sitting at my desk wearing my badge and answering my emails.`,'point','office'),
      scene('B',`He looks exactly like you, but he finished the entire quarterly report before breakfast.`,'look','office'),
      scene('A',`That proves he is fake. I have been avoiding that report for three weeks.`,'gesture','office','funny'),
      scene('B',`Management already promoted him. They want you to train your replacement before lunch.`,'hand-object','office','funny'),
      scene('A',`He just whispered that he is not replacing me. He is hiding from the next copy.`,'step-back','office'),
      scene('B',`The elevator opened. There are twelve more of you, and every one has a better résumé.`,'open-door','office'),
      scene('A',`Lock the conference room. We need to find out which copy arrived first.`,'run','office'),
      scene('B',`Too late. The calendar says this meeting has repeated every day for a year.`,'phone','office'),
      scene('A',`Then the original me already escaped ${place}. The copies are the ones still working.`,'laugh','office','funny')
    ]
  },
  {
    id:'shadow-parking', genre:'horror', title:'My Shadow Parked First',
    build:({A,B,time}) => [
      scene('B',`${A}, your shadow is standing beside the car, but you are standing next to me.`,'point','garage'),
      scene('A',`Do not move. It only changes position when the lights flicker.`,'freeze','garage'),
      scene('B',`It is holding the keys. You left those in my hand at ${time}.`,'hand-object','garage'),
      scene('A',`The headlights turned on. There is another shadow sitting in the driver's seat.`,'look','garage'),
      scene('B',`Mine is gone now. Please tell me it did not just climb into the back seat.`,'turn','garage'),
      scene('A',`The car doors locked themselves. The dashboard says two passengers already inside.`,'phone','garage'),
      scene('B',`Our shadows are driving away, but the real car has not moved at all.`,'run','garage'),
      scene('A',`Every garage light is switching off toward us, one row at a time.`,'step-back','garage'),
      scene('B',`Run before the last light dies. Whatever leaves here will be wearing our shapes.`,'run','garage')
    ]
  },
  {
    id:'cafe-tomorrow', genre:'mystery', title:'The Customer From Tomorrow',
    build:({A,B,object}) => [
      scene('A',`${B}, that customer ordered my exact drink and paid with a coin dated next year.`,'point','cafe'),
      scene('B',`He also left this ${object} for you. Your name is engraved on the back.`,'hand-object','cafe'),
      scene('A',`It is playing a recording of us having this conversation, word for word.`,'phone','cafe'),
      scene('B',`The next line says we should leave before the cup breaks. Do not touch anything.`,'step-back','cafe'),
      scene('A',`The cup broke by itself. Everyone in the café just froze except that customer.`,'freeze','cafe'),
      scene('B',`He says this is the only minute today that can be changed.`,'look','cafe'),
      scene('A',`He wants us to stop him from walking through that door thirty seconds ago.`,'point','cafe'),
      scene('B',`Then who is the man outside waving at us with your face?`,'turn','street'),
      scene('A',`The recording ended with one sentence: never let tomorrow meet itself.`,'run','street')
    ]
  },
  {
    id:'motel-404', genre:'horror', title:'Room 404 Was My Bedroom',
    build:({A,B,place}) => [
      scene('B',`${A}, the desk clerk gave us room 404, then insisted this motel has only three floors.`,'hand-object','motel'),
      scene('A',`The key still opened something. This room looks exactly like my childhood bedroom.`,'open-door','bedroom'),
      scene('B',`Those are your photographs on the wall, but I appear in every one of them.`,'point','bedroom'),
      scene('A',`We did not meet until college. Why does that picture say ${place}, ten years earlier?`,'look','bedroom'),
      scene('B',`The phone is ringing. The display says front desk, twenty years ago.`,'phone','bedroom'),
      scene('A',`The clerk says checkout happened already and the room must be empty before midnight.`,'step-back','bedroom'),
      scene('B',`Someone is knocking from inside the closet. They are using our voices.`,'freeze','bedroom'),
      scene('A',`The hallway is gone. The room door opens into this same bedroom again.`,'open-door','bedroom'),
      scene('B',`Then room 404 is not missing. It is where the motel puts people it wants forgotten.`,'hide','bedroom')
    ]
  },
  {
    id:'duck-detective', genre:'comedy', title:'The Detective Had Feathers',
    build:({A,B,object}) => [
      scene('A',`${B}, that duck has followed me for three days, and now it is wearing a tiny badge.`,'point','park','funny'),
      scene('B',`He slid a photograph under the bench. It shows you stealing a golden ${object}.`,'hand-object','park','funny'),
      scene('A',`I have never seen that thing in my life, and ducks do not run criminal investigations.`,'gesture','park','funny'),
      scene('B',`This one does. He has a notebook, two witnesses, and surprisingly neat handwriting.`,'look','park','funny'),
      scene('A',`Tell Detective Quacks I want a lawyer and one reasonable explanation.`,'point','park','funny'),
      scene('B',`He says the ${object} was hidden in your lunch bag. Check it slowly.`,'reach','park','funny'),
      scene('A',`It is in here, along with a note thanking me for taking the blame.`,'hand-object','park','funny'),
      scene('B',`The duck just arrested a squirrel. Apparently we cracked an international snack ring.`,'laugh','park','funny'),
      scene('A',`Great. I am innocent, but Detective Quacks says I still owe him breadcrumbs.`,'handshake','park','funny')
    ]
  }
];

const PLACES = ['the Hawthorne building','the old Riverside block','the Bellweather complex','the Northline apartments'];
const TIMES = ['3:17 a.m.','11:58 p.m.','exactly midnight','2:06 a.m.'];
const OBJECTS = ['silver key','red notebook','broken watch','green jacket','glass marble','brass compass'];
const SAFE_ACTIONS = new Set(['point','step-back','reach','knock','open-door','slam-door','look','turn','phone','run','freeze','hand-object','pull','gesture','laugh','handshake','hide','walk','wave']);
const SAFE_SETTINGS = new Set(['hallway','kitchen','apartment','laundromat','elevator','lobby','bus','street','shop','office','garage','cafe','motel','bedroom','park']);

function proceduralStory(seedValue, { long = false } = {}) {
  const seed = hashSeed(seedValue);
  const pair = CHARACTER_PAIRS[seed % CHARACTER_PAIRS.length].map(character => ({ ...character }));
  const slotMatch = String(seedValue).match(/^(.*)-slot-(\d+)$/);
  const plotIndex = slotMatch
    ? (hashSeed(slotMatch[1]) + Math.max(0,Number(slotMatch[2]) - 1)) % PLOTS.length
    : (seed >>> 3) % PLOTS.length;
  const plot = PLOTS[plotIndex];
  const vars = {
    A: pair[0].name,
    B: pair[1].name,
    place: pick(PLACES, seed, 1),
    time: pick(TIMES, seed, 2),
    object: pick(OBJECTS, seed, 3)
  };
  let scenes = plot.build(vars);

  const naturalExtensions = [
    'Tell me you can see that too.',
    'Stay close, because something is definitely wrong.',
    'Do not move until we understand this.',
    'That was not happening a second ago.',
    'We need a real plan right now.',
    'Look again, because it just changed.',
    'Keep watching and do not touch anything.',
    'I have a very bad feeling.',
    'Whatever happens next, stay beside me.'
  ];
  scenes = scenes.map((item,index) => ({
    ...item,
    dialogue: `${item.dialogue} ${naturalExtensions[index % naturalExtensions.length]}`
  }));

  if (long) {
    scenes = scenes.concat([
      scene('A',`We made it outside, but every window behind us shows the room we just escaped.`,'run','street'),
      scene('B',`My phone says the story is not over. It is asking which one of us opened it first.`,'phone','street'),
      scene('A',`Do not answer. The moment we choose, whatever followed us will know whose voice to use.`,'step-back','street')
    ]);
  }

  return {
    id: `${plot.id}-${seedValue}`,
    title: plot.title,
    genre: plot.genre,
    characters: pair,
    scenes,
    caption: `${plot.title}: a normal moment turns impossible. Watch to the end. #RubysRealm #AnimatedStory #StoryTok #${plot.genre.replace(/[^a-z]/gi,'')} #AIGenerated`
  };
}

function normalizeGeneratedStory(generated, base, long) {
  const desiredScenes = long ? 12 : 9;
  if (!generated || typeof generated !== 'object') throw new Error('Generated story is not an object.');
  if (!Array.isArray(generated.scenes) || generated.scenes.length < desiredScenes - 2) {
    throw new Error('Generated story did not contain enough scenes.');
  }

  const scenes = generated.scenes.slice(0, desiredScenes).map((item, index) => {
    const speaker = item.speaker === 'B' ? 'B' : 'A';
    const dialogue = String(item.dialogue || '').trim().slice(0, 240);
    if (dialogue.length < 8) throw new Error(`Generated scene ${index + 1} has no dialogue.`);
    return {
      speaker,
      dialogue,
      action: SAFE_ACTIONS.has(item.action) ? item.action : 'gesture',
      setting: SAFE_SETTINGS.has(item.setting) ? item.setting : base.scenes[Math.min(index, base.scenes.length - 1)].setting,
      mood: item.mood === 'funny' ? 'funny' : 'tense'
    };
  });

  return {
    ...base,
    title: String(generated.title || base.title).trim().slice(0, 80),
    genre: String(generated.genre || base.genre).trim().slice(0, 30),
    scenes,
    caption: `${String(generated.title || base.title).trim().slice(0, 80)}. Watch to the end. #RubysRealm #AnimatedStory #StoryTok #AIGenerated`
  };
}

async function aiStory(seedValue, base, { long = false } = {}) {
  const [first, second] = base.characters;
  const sceneCount = long ? 12 : 9;
  const prompt = `Create one original ${base.genre} TikTok story inspired by the title "${base.title}".

Requirements:
- Exactly two visible ADULT characters: ${first.name} (speaker A) and ${second.name} (speaker B).
- Exactly ${sceneCount} chronological scenes with a clear hook, escalation, physical action, twist, and final cliffhanger/payoff.
- 150-190 total spoken words${long ? ', or 210-250 words for this longer edition' : ''}.
- Every scene must have one speaker talking to the other. No narrator and no silent scenes.
- Dialogue must sound natural, fast, and emotionally acted. Avoid exposition dumps.
- Keep it PG-13: no gore, hate, sexual content, real-person impersonation, or copyrighted characters.
- action must be one of: ${[...SAFE_ACTIONS].join(', ')}.
- setting must be one of: ${[...SAFE_SETTINGS].join(', ')}.
- mood must be "tense" or "funny".
- Do not include hashtags, stage directions inside dialogue, or a watermark.
- Seed: ${seedValue}.

Return only JSON in this exact shape:
{"title":"...","genre":"...","scenes":[{"speaker":"A","dialogue":"...","action":"point","setting":"hallway","mood":"tense"}]}`;
  const generated = await generateStoryJson(prompt);
  return normalizeGeneratedStory(generated, base, long);
}

export async function createStory(seedValue, options = {}) {
  const base = proceduralStory(seedValue, options);
  if (!hasGatewayAuth() || process.env.AI_STORY_GENERATION === 'off') return base;

  try {
    return await aiStory(seedValue, base, options);
  } catch (error) {
    console.warn('AI story generation failed; using deterministic story', error.message);
    return base;
  }
}

export function previewStory(seedValue, options = {}) {
  return proceduralStory(seedValue, options);
}
