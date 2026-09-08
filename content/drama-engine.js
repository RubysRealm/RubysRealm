import { generateStoryJson, hasGatewayAuth } from '../lib/ai-gateway.js';

const SERIES = [
  {
    title: 'The Contract Wife Next Door',
    genre: 'romance-thriller',
    logline: 'A broke mechanic agrees to a fake marriage with the guarded heiress next door and learns her family is hiding why she chose him.',
    setting: 'modern city',
    characters: [
      { id: 'A', name: 'Evan', voice: 'onyx', role: 'mechanic' },
      { id: 'B', name: 'Lena', voice: 'nova', role: 'heiress' },
      { id: 'C', name: 'Victor', voice: 'echo', role: 'family attorney' }
    ]
  },
  {
    title: 'The CEO Who Fired the Wrong Girl',
    genre: 'romance-drama',
    logline: 'A ruthless founder fires a temp employee, then discovers she owns the patent keeping his company alive.',
    setting: 'high-rise office',
    characters: [
      { id: 'A', name: 'Maya', voice: 'nova', role: 'inventor' },
      { id: 'B', name: 'Cole', voice: 'onyx', role: 'CEO' },
      { id: 'C', name: 'Nora', voice: 'shimmer', role: 'chief of staff' }
    ]
  },
  {
    title: 'My Brother Left Me a Locked Hotel',
    genre: 'mystery-drama',
    logline: 'A woman inherits a nearly empty hotel where one floor is sealed and every employee refuses to say why.',
    setting: 'old luxury hotel',
    characters: [
      { id: 'A', name: 'Renee', voice: 'shimmer', role: 'new owner' },
      { id: 'B', name: 'Miles', voice: 'echo', role: 'night manager' },
      { id: 'C', name: 'June', voice: 'nova', role: 'housekeeper' }
    ]
  }
];

const FALLBACK_EPISODES = [
  ['A stranger delivers a contract that names the lead character.', 'The second lead admits the contract is real but refuses to explain one clause.', 'A third character arrives and warns them not to sign.', 'The lead notices the document was dated two weeks before they met.', 'They sign anyway to force the truth out.', 'A hidden phone starts ringing inside the contract envelope.'],
  ['The phone contains one video recorded tomorrow.', 'The video shows the two leads arguing in a place neither recognizes.', 'A background detail links the scene to the third character.', 'They confront the third character and get a partial confession.', 'The confession changes what the first episode meant.', 'Someone deletes the future video remotely while they are watching it.'],
  ['The leads follow the clue to a private office after hours.', 'They find a second contract with a different signature.', 'One lead realizes the arrangement was designed around them personally.', 'The third character catches them and locks the office.', 'They escape through a service corridor.', 'The corridor opens into a room filled with photos of the lead.'],
  ['The photos span years, including dates before the characters met.', 'One photo contains a person believed to be dead.', 'The leads disagree about whether to call the police.', 'A new message demands the signed contract in exchange for answers.', 'They make a copy and set a trap.', 'The person who arrives for the exchange is someone they both trust.'],
  ['The trusted person claims the entire situation was meant to protect them.', 'A hidden financial motive comes to light.', 'The romantic tension turns into a direct accusation.', 'The leads separate to verify different parts of the story.', 'Both discover evidence that supports opposite explanations.', 'One receives proof that the other has been lying from the beginning.'],
  ['The apparent lie is revealed to be a cover for a more dangerous truth.', 'The third character loses control of the plan.', 'The leads are forced to work together again.', 'They uncover the original event that started the conspiracy.', 'A final document reveals who actually benefited.', 'The supposed mastermind is shown taking orders from someone else.'],
  ['The real mastermind steps into the open.', 'The leads learn why they were chosen specifically.', 'The contract becomes leverage rather than a trap.', 'They turn the plan back on the mastermind.', 'The third character switches sides at the worst possible moment.', 'The episode ends with the lead apparently losing everything.'],
  ['The loss was partly staged.', 'The leads use the final clause of the contract against the mastermind.', 'The third character gives up the missing evidence.', 'The conspiracy collapses publicly.', 'The leads finally decide what their relationship actually is.', 'A last unexplained message leaves room for another season.']
];

function hashSeed(value) {
  let h = 2166136261;
  for (const c of String(value)) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function pick(list, seed, offset = 0) {
  return list[((seed + Math.imul(offset + 1, 2654435761)) >>> 0) % list.length];
}

function cleanLine(value) {
  let s = String(value || '').replace(/\s+/g, ' ').trim();
  if (!s) return '';
  if (s.split(/\s+/).length > 28) s = s.split(/\s+/).slice(0, 28).join(' ');
  if (!/[.!?]$/.test(s)) s += '.';
  return s;
}

function fallbackEpisode(seedValue, episodeNumber) {
  const seed = hashSeed(seedValue);
  const series = pick(SERIES, seed, 2);
  const ep = Math.min(8, Math.max(1, Number(episodeNumber) || 1));
  const beats = FALLBACK_EPISODES[ep - 1];
  const scenes = [];
  let n = 0;
  for (const beat of beats) {
    const speaker = series.characters[n % 2];
    const other = series.characters[(n + 1) % 2];
    scenes.push({ speaker: speaker.id, dialogue: cleanLine(`${other.name}, ${beat}`), beat, mood: n < 2 ? 'urgent' : n < 5 ? 'tense' : 'cliffhanger' });
    n += 1;
    scenes.push({ speaker: other.id, dialogue: cleanLine(n % 3 === 0 ? 'That changes everything. Tell me what you are not saying.' : 'I do not like this, but we keep going until we know who set this up.'), beat, mood: 'tense' });
    n += 1;
  }
  return {
    platform: 'original-short-drama-v1',
    originalOnly: true,
    referenceStyle: 'fast serialized vertical short drama',
    seriesTitle: series.title,
    episodeTitle: `Episode ${ep}`,
    episodeNumber: ep,
    totalEpisodes: 8,
    genre: series.genre,
    logline: series.logline,
    setting: series.setting,
    characters: series.characters,
    targetSeconds: 68,
    scenes,
    cliffhanger: beats[beats.length - 1]
  };
}

function sanitizeGenerated(raw, seedValue, episodeNumber) {
  if (!raw || !Array.isArray(raw.scenes)) return null;
  const base = fallbackEpisode(seedValue, episodeNumber);
  const validIds = new Set(base.characters.map(c => c.id));
  const scenes = raw.scenes
    .map((s, i) => ({
      speaker: validIds.has(s?.speaker) ? s.speaker : base.characters[i % 2].id,
      dialogue: cleanLine(s?.dialogue),
      beat: String(s?.beat || '').slice(0, 180),
      mood: ['romantic', 'urgent', 'tense', 'angry', 'sad', 'cliffhanger'].includes(s?.mood) ? s.mood : 'tense'
    }))
    .filter(s => s.dialogue.length > 8)
    .slice(0, 18);
  if (scenes.length < 10) return null;
  return {
    ...base,
    seriesTitle: String(raw.seriesTitle || base.seriesTitle).slice(0, 80),
    episodeTitle: String(raw.episodeTitle || base.episodeTitle).slice(0, 80),
    scenes,
    cliffhanger: String(raw.cliffhanger || base.cliffhanger).slice(0, 220)
  };
}

async function aiEpisode(seedValue, episodeNumber) {
  const base = fallbackEpisode(seedValue, episodeNumber);
  const previous = episodeNumber > 1 ? FALLBACK_EPISODES[Math.max(0, episodeNumber - 2)].join(' ') : 'This is the series premiere.';
  const prompt = `Create episode ${base.episodeNumber} of an ORIGINAL 8-episode vertical short-drama series. Do not copy, adapt, paraphrase, or reuse any identifiable plot, scene, dialogue, character, title, or footage from ShortMax, ShortTV, ReelShort, DramaBox, or any other show. Those services are only a pacing/format reference.\n\nSeries: ${base.seriesTitle}\nGenre: ${base.genre}\nPremise: ${base.logline}\nRecurring characters: ${base.characters.map(c => `${c.id}=${c.name} (${c.role})`).join(', ')}\nPrior-episode direction: ${previous}\n\nReturn JSON only with seriesTitle, episodeTitle, cliffhanger, and scenes. Produce 12-16 scenes totaling roughly 60-80 seconds of spoken dialogue. Each scene must contain speaker (A/B/C), dialogue, beat, mood. Dialogue should sound like live-action drama: short, emotionally clear, no narration, no exposition dumps, no repetitive catchphrases. Start with a hook in the first 2 seconds, reveal something meaningful every 10-15 seconds, and end on a strong cliffhanger. Keep continuity with the recurring characters. No copyrighted characters or brands.`;
  const raw = await generateStoryJson(prompt);
  return sanitizeGenerated(raw, seedValue, episodeNumber);
}

export async function createDramaEpisode(seedValue = new Date().toISOString().slice(0, 10), episodeNumber = 1) {
  if (hasGatewayAuth()) {
    try {
      const generated = await aiEpisode(seedValue, Number(episodeNumber) || 1);
      if (generated) return generated;
    } catch (error) {
      console.warn('AI drama generation failed; using procedural original episode', error.message);
    }
  }
  return fallbackEpisode(seedValue, Number(episodeNumber) || 1);
}

export function previewDramaEpisode(seedValue, episodeNumber = 1) {
  return fallbackEpisode(seedValue, episodeNumber);
}
