import sharp from 'sharp';
import { createRemoteJWKSet, jwtVerify } from 'jose';
import { getVercelOidcToken } from '@vercel/oidc';

const GITHUB_JWKS = createRemoteJWKSet(new URL('https://token.actions.githubusercontent.com/.well-known/jwks'));
const AUDIENCE = 'rubys-realm-image-generator';
const REPOSITORY = 'RubysRealm/RubysRealm';
const WORKFLOW = '.github/workflows/tiktok-animated-story.yml';
const GATEWAY = 'https://ai-gateway.vercel.sh/v1';

async function verifyCaller(auth) {
  const token = String(auth || '').replace(/^Bearer\s+/i, '').trim();
  if (!token) throw new Error('Missing GitHub Actions OIDC token.');
  const { payload } = await jwtVerify(token, GITHUB_JWKS, {
    issuer: 'https://token.actions.githubusercontent.com',
    audience: AUDIENCE,
  });
  if (payload.repository !== REPOSITORY) throw new Error('OIDC repository is not authorized.');
  if (payload.ref !== 'refs/heads/main') throw new Error('OIDC ref is not authorized.');
  const workflowRef = String(payload.workflow_ref || '');
  if (!workflowRef.includes(`${REPOSITORY}/${WORKFLOW}@refs/heads/main`)) {
    throw new Error('OIDC workflow is not authorized.');
  }
  if (!['push', 'schedule', 'workflow_dispatch'].includes(String(payload.event_name || ''))) {
    throw new Error('OIDC event is not authorized.');
  }
}

async function gatewayToken() {
  if (process.env.AI_GATEWAY_API_KEY) return process.env.AI_GATEWAY_API_KEY;
  try {
    return await getVercelOidcToken();
  } catch {
    return null;
  }
}

async function creditBalance(token) {
  const r = await fetch(`${GATEWAY}/credits`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  if (!r.ok) throw new Error(`AI Gateway credits check failed (${r.status}).`);
  const data = await r.json();
  const balance = Number(data.balance || 0);
  if (!Number.isFinite(balance)) throw new Error('AI Gateway returned an invalid credit balance.');
  return balance;
}

function oneLine(value, max = 1600) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ ok: false, error: 'Method not allowed' });

  try {
    await verifyCaller(req.headers.authorization);

    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    const beat = oneLine(body.beat);
    const previousBeat = oneLine(body.previousBeat);
    const nextBeat = oneLine(body.nextBeat);
    const title = oneLine(body.title, 240);
    const occupation = oneLine(body.occupation, 160);
    const part = oneLine(body.part, 60);
    const index = Number(body.index);
    const seed = Number(body.seed || 0);
    const protagonist = body.protagonist && typeof body.protagonist === 'object'
      ? oneLine(body.protagonist.description, 700)
      : '';

    if (!beat) throw new Error('Exact current narration beat is required.');
    if (!Number.isInteger(index) || index < 0 || index > 80) throw new Error('Invalid scene index.');
    if (!occupation) throw new Error('Complete occupation is required.');

    const token = await gatewayToken();
    if (!token) throw new Error('Vercel AI Gateway authorization is unavailable.');

    const reserve = Number(process.env.AI_IMAGE_CREDIT_RESERVE || 0.05);
    const balance = await creditBalance(token);
    if (balance <= reserve) {
      return res.status(402).json({
        ok: false,
        error: 'Existing AI Gateway credit reserve reached; no paid top-up will be attempted.',
        balance,
        reserve,
      });
    }

    const model = process.env.AI_IMAGE_MODEL || 'google/gemini-3.1-flash-image-preview';

    const prompt = [
      'Create exactly ONE fresh vertical 9:16 illustration for a narrated TikTok story.',
      'VISUAL REFERENCE: match the latest user-supplied photo examples: polished simple non-realistic adult cartoon artwork, clean dark outlines, compact expressive adult proportions, restrained facial features, soft cel shading, colorful scene-specific environment, mobile-friendly composition.',
      'Do not imitate photography. Do not create realistic skin, camera-real faces, stock-photo aesthetics, 3D photorealism, anime, a collage, split screen, inset panels, or a talking-head narrator.',
      'LITERAL BEAT RULE: the picture must visibly show the exact place, people, objects, and action stated in CURRENT BEAT. A viewer should understand the current narrated event from the picture alone.',
      'SCENE VARIETY RULE: use the location and props demanded by this beat. Do not recycle a generic storefront, phone, car, desk, hallway, sign, room, cash register, or other prop unless CURRENT BEAT explicitly requires it.',
      'CONTINUITY RULE: keep recurring people visually consistent across the story, but change pose, action, clothing context, camera staging, location, weather, lighting, and objects whenever the narration changes them.',
      protagonist ? `Recurring protagonist bible: ${protagonist}.` : '',
      'TEXT RULE: absolutely no text, captions, signs with readable writing, logos, labels, UI, subtitles, speech bubbles, or watermarks inside the generated artwork.',
      'COMPOSITION RULE: one coherent full-frame scene. Keep important action clear in the center and lower-middle while leaving enough visual breathing room near the top for a persistent title overlay and near the lower center for one-word captions.',
      `Series title: ${title}. Occupation: ${occupation}. ${part}.`,
      previousBeat ? `Previous beat for continuity only: ${previousBeat}` : '',
      `CURRENT BEAT TO ILLUSTRATE LITERALLY: ${beat}`,
      nextBeat ? `Next beat for continuity only; do not depict it early: ${nextBeat}` : '',
      `Scene index: ${index}. Fresh-generation nonce: ${seed}.`,
      'Generate only the current scene. Do not include events from the previous or next beat unless the current beat itself states them.'
    ].filter(Boolean).join(' ');

    const r = await fetch(`${GATEWAY}/images/generations`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model,
        prompt,
        n: 1,
        response_format: 'b64_json',
      }),
      cache: 'no-store',
    });

    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const detail = String(data?.error?.message || data?.message || 'unknown error').slice(0, 400);
      throw new Error(`AI image generation failed (${r.status}): ${detail}`);
    }

    const item = (data.data || [])[0] || {};
    let input;
    if (item.b64_json) {
      input = Buffer.from(item.b64_json, 'base64');
    } else if (item.url) {
      const ir = await fetch(item.url, { cache: 'no-store' });
      if (!ir.ok) throw new Error(`Generated image download failed (${ir.status}).`);
      input = Buffer.from(await ir.arrayBuffer());
    } else {
      throw new Error('AI Gateway returned no image data.');
    }

    const output = await sharp(input)
      .rotate()
      .resize(1080, 1920, { fit: 'cover', position: 'centre' })
      .jpeg({ quality: 94, chromaSubsampling: '4:4:4' })
      .toBuffer();

    res.setHeader('Content-Type', 'image/jpeg');
    res.setHeader('Cache-Control', 'no-store, max-age=0');
    res.setHeader('X-Rubys-Realm-Platform', 'clean-rebuild-v1');
    res.setHeader('X-Rubys-Realm-Image-Model', model);
    res.setHeader('X-Rubys-Realm-Scene-Index', String(index));
    return res.status(200).send(output);
  } catch (e) {
    console.error('clean rebuild story-image failed', e);
    return res.status(500).json({ ok: false, error: e.message });
  }
}
