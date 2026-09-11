import crypto from 'node:crypto';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const sodium = require('libsodium-wrappers');

const OWNER = 'RubysRealm';
const REPO = 'RubysRealm';
const API = 'https://api.github.com';

async function github(path, token, options = {}) {
  return fetch(`${API}${path}`, {
    ...options,
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
      ...(options.headers || {})
    }
  });
}

function validControlKey(value) {
  try {
    return Buffer.from(String(value || ''), 'base64url').length === 32;
  } catch {
    return false;
  }
}

async function putSecret(name, value, token, publicKey) {
  const repoPublicKey = sodium.from_base64(publicKey.key, sodium.base64_variants.ORIGINAL);
  const encrypted = sodium.crypto_box_seal(sodium.from_string(value), repoPublicKey);
  const encryptedValue = sodium.to_base64(encrypted, sodium.base64_variants.ORIGINAL);
  return github(`/repos/${OWNER}/${REPO}/actions/secrets/${name}`, token, {
    method: 'PUT',
    body: JSON.stringify({ encrypted_value: encryptedValue, key_id: publicKey.key_id })
  });
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ ok: false, error: 'POST_REQUIRED' });
  }

  const token = String(req.body?.token || '').trim();
  if (token.length < 20 || token.length > 500) {
    return res.status(400).json({ ok: false, error: 'INVALID_GITHUB_TOKEN' });
  }

  const requestedKey = String(req.body?.controlKey || '').trim();
  if (requestedKey && !validControlKey(requestedKey)) {
    return res.status(400).json({ ok: false, error: 'INVALID_CONTROL_KEY', message: 'The saved Social Bot key is invalid. Reset phone authorization and try again.' });
  }

  const gmailAppPassword = String(req.body?.gmailAppPassword || '').replace(/\s+/g, '').trim();
  if (gmailAppPassword && (gmailAppPassword.length < 8 || gmailAppPassword.length > 128)) {
    return res.status(400).json({ ok: false, error: 'INVALID_GMAIL_APP_PASSWORD', message: 'The Gmail App Password does not look valid.' });
  }

  try {
    const repoCheck = await github(`/repos/${OWNER}/${REPO}`, token, { method: 'GET' });
    if (!repoCheck.ok) {
      return res.status(repoCheck.status).json({ ok: false, error: 'REPOSITORY_ACCESS_FAILED', message: 'This token cannot access RubysRealm/RubysRealm.' });
    }

    const workflowCheck = await github(`/repos/${OWNER}/${REPO}/actions/workflows/social-bot.yml`, token, { method: 'GET' });
    if (!workflowCheck.ok) {
      return res.status(workflowCheck.status).json({ ok: false, error: 'ACTIONS_ACCESS_FAILED', message: 'Give the token Actions read/write access for RubysRealm/RubysRealm.' });
    }

    const keyResponse = await github(`/repos/${OWNER}/${REPO}/actions/secrets/public-key`, token, { method: 'GET' });
    if (!keyResponse.ok) {
      return res.status(keyResponse.status).json({ ok: false, error: 'SECRETS_ACCESS_FAILED', message: 'Give the token Secrets read/write access for RubysRealm/RubysRealm.' });
    }

    const publicKey = await keyResponse.json();
    await sodium.ready;

    // Reuse the phone's existing key on retries so authorization cannot silently rotate
    // the worker key and make previously encrypted state unreadable.
    const controlKey = requestedKey || crypto.randomBytes(32).toString('base64url');
    const controlSecret = await putSecret('SOCIALBOT_KEY', controlKey, token, publicKey);
    if (!controlSecret.ok) {
      return res.status(controlSecret.status).json({ ok: false, error: 'SECRET_INSTALL_FAILED', message: 'GitHub would not install the Social Bot key. Make sure the token has Secrets read/write access.' });
    }

    let gmailConfigured = false;
    if (gmailAppPassword) {
      const gmailSecret = await putSecret('SOCIALBOT_GMAIL_APP_PASSWORD', gmailAppPassword, token, publicKey);
      if (!gmailSecret.ok) {
        return res.status(gmailSecret.status).json({ ok: false, error: 'GMAIL_SECRET_INSTALL_FAILED', message: 'The Social Bot key was saved, but GitHub would not save the Gmail App Password.' });
      }
      gmailConfigured = true;
    }

    return res.status(200).json({ ok: true, key: controlKey, gmailConfigured, message: 'Social Bot backend setup complete.' });
  } catch (error) {
    return res.status(500).json({ ok: false, error: 'SETUP_FAILED', message: 'Social Bot setup failed before completion.' });
  }
}
