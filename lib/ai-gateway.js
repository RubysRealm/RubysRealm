const GATEWAY_BASE = 'https://ai-gateway.vercel.sh';

let cachedStoryModel;

function authToken() {
  return String(process.env.AI_GATEWAY_API_KEY || process.env.VERCEL_OIDC_TOKEN || '').trim();
}

async function gatewayJson(path, options = {}) {
  const token = authToken();
  if (!token) throw new Error('AI Gateway authentication is unavailable.');

  const response = await fetch(`${GATEWAY_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(options.headers || {})
    }
  });

  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.error?.message || body?.message || `HTTP ${response.status}`;
    throw new Error(`AI Gateway request failed: ${detail}`);
  }
  return body;
}

function numericPrice(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : Number.POSITIVE_INFINITY;
}

async function chooseStoryModel() {
  if (process.env.AI_STORY_MODEL) return process.env.AI_STORY_MODEL;
  if (cachedStoryModel) return cachedStoryModel;

  try {
    const response = await fetch(`${GATEWAY_BASE}/v1/models`);
    const body = await response.json();
    const languageModels = (body?.data || []).filter(model => model.type === 'language');
    const preferredPatterns = [
      /openai\/gpt-5\.6-luna$/i,
      /google\/gemini-3(?:\.\d+)?-flash/i,
      /anthropic\/claude-(?:haiku|instant)/i,
      /(?:mini|nano|flash|haiku|luna)/i
    ];

    for (const pattern of preferredPatterns) {
      const matches = languageModels
        .filter(model => pattern.test(model.id))
        .sort((a, b) => numericPrice(a.pricing?.output) - numericPrice(b.pricing?.output));
      if (matches[0]?.id) {
        cachedStoryModel = matches[0].id;
        return cachedStoryModel;
      }
    }
  } catch (error) {
    console.warn('AI Gateway model discovery failed', error.message);
  }

  cachedStoryModel = 'openai/gpt-5.6-sol';
  return cachedStoryModel;
}

function parseJsonText(value) {
  const text = String(value || '').trim();
  const unfenced = text
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/, '')
    .trim();
  return JSON.parse(unfenced);
}

export function hasGatewayAuth() {
  return Boolean(authToken());
}

export async function generateStoryJson(prompt) {
  const model = await chooseStoryModel();
  const result = await gatewayJson('/v1/chat/completions', {
    method: 'POST',
    body: JSON.stringify({
      model,
      messages: [
        {
          role: 'system',
          content: 'You write original, fast-moving vertical animated stories. Return only valid JSON and never use copyrighted characters.'
        },
        { role: 'user', content: prompt }
      ],
      temperature: 0.92,
      max_tokens: 1800
    })
  });

  return parseJsonText(result?.choices?.[0]?.message?.content);
}

export async function generateSpeechAudio({ text, voice, speed = 0.96 }) {
  const model = process.env.AI_SPEECH_MODEL || 'openai/tts-1';
  const result = await gatewayJson('/v4/ai/speech-model', {
    method: 'POST',
    headers: { 'ai-model-id': model },
    body: JSON.stringify({
      text,
      voice,
      outputFormat: 'wav',
      speed,
      language: 'en',
      instructions: 'Natural conversational acting. Use clear emotion, quick TikTok pacing, and no announcer voice.'
    })
  });

  if (!result?.audio) throw new Error('AI Gateway returned no speech audio.');
  return Buffer.from(result.audio, 'base64');
}
