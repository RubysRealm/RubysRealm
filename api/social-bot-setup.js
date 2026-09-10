import crypto from 'node:crypto';
import sodium from 'libsodium-wrappers';

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

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ ok: false, error: 'POST_REQUIRED' });
  }

  const token = String(req.body?.token || '').trim();
  if (token.length < 20 || token.length > 500) {
    return res.status(400).json({ ok: false, error: 'INVALID_GITHUB_TOKEN' });
  }

  try {
    // Verify the token can see the target repository.
    const repoCheck = await github(`/repos/${OWNER}/${REPO}`, token, { method: 'GET' });
    if (!repoCheck.ok) {
      return res.status(repoCheck.status).json({
        ok: false,
        error: 'REPOSITORY_ACCESS_FAILED',
        message: 'This token cannot access RubysRealm/RubysRealm.'
      });
    }

    // Verify workflow-dispatch access before changing anything.
    const workflowCheck = await github(`/repos/${OWNER}/${REPO}/actions/workflows/social-bot.yml`, token, { method: 'GET' });
    if (!workflowCheck.ok) {
      return res.status(workflowCheck.status).json({
        ok: false,
        error: 'ACTIONS_ACCESS_FAILED',
        message: 'Give the token Actions read/write access for RubysRealm/RubysRealm.'
      });
    }

    // GitHub requires Actions secrets to be encrypted with the repository public key.
    const keyResponse = await github(`/repos/${OWNER}/${REPO}/actions/secrets/public-key`, token, { method: 'GET' });
    if (!keyResponse.ok) {
      return res.status(keyResponse.status).json({
        ok: false,
        error: 'SECRETS_ACCESS_FAILED',
        message: 'Give the token Secrets read/write access for RubysRealm/RubysRealm.'
      });
    }

    const publicKey = await keyResponse.json();
    await sodium.ready;

    const controlKey = crypto.randomBytes(32).toString('base64url');
    const repoPublicKey = sodium.from_base64(publicKey.key, sodium.base64_variants.ORIGINAL);
    const encrypted = sodium.crypto_box_seal(sodium.from_string(controlKey), repoPublicKey);
    const encryptedValue = sodium.to_base64(encrypted, sodium.base64_variants.ORIGINAL);

    const putSecret = await github(`/repos/${OWNER}/${REPO}/actions/secrets/SOCIALBOT_KEY`, token, {
      method: 'PUT',
      body: JSON.stringify({
        encrypted_value: encryptedValue,
        key_id: publicKey.key_id
      })
    });

    if (!putSecret.ok) {
      return res.status(putSecret.status).json({
        ok: false,
        error: 'SECRET_INSTALL_FAILED',
        message: 'GitHub would not install the Social Bot key. Make sure the token has Secrets read/write access.'
      });
    }

    return res.status(200).json({
      ok: true,
      key: controlKey,
      message: 'Social Bot backend setup complete.'
    });
  } catch (error) {
    return res.status(500).json({
      ok: false,
      error: 'SETUP_FAILED',
      message: 'Social Bot setup failed before completion.'
    });
  }
}
