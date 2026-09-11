(() => {
  const TOKEN_KEY = 'socialbot_gh_token';
  const KEY_KEY = 'socialbot_key';
  const SETUP_KEY = 'socialbot_setup_v2';
  const GMAIL_SAVED_KEY = 'socialbot_gmail_saved_at';
  const RAW_STATUS = 'https://raw.githubusercontent.com/RubysRealm/RubysRealm/social-bot-state/social-bot/status.json';
  const nativeFetch = window.fetch.bind(window);

  function b64u(bytes) {
    let s = '';
    bytes.forEach(b => { s += String.fromCharCode(b); });
    return btoa(s).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
  }

  function ensureControlKey() {
    let key = localStorage.getItem(KEY_KEY) || '';
    if (!key) {
      if (localStorage.getItem(SETUP_KEY) === 'done') localStorage.removeItem(SETUP_KEY);
      key = b64u(crypto.getRandomValues(new Uint8Array(32)));
      localStorage.setItem(KEY_KEY, key);
    }
    return key;
  }

  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : (input?.url || '');
    if (url.includes('/api/social-bot-setup') && String(init.method || 'GET').toUpperCase() === 'POST') {
      try {
        const body = JSON.parse(init.body || '{}');
        if (body.token) {
          body.token = String(body.token).trim();
          localStorage.setItem(TOKEN_KEY, body.token);
        }
        if (!body.controlKey) body.controlKey = ensureControlKey();
        init = { ...init, body: JSON.stringify(body) };
      } catch {}
    }
    return nativeFetch(input, init);
  };

  function wireTokenPersistence() {
    const input = document.getElementById('setupToken');
    if (!input || input.dataset.persistWired) return;
    input.dataset.persistWired = '1';
    const saved = localStorage.getItem(TOKEN_KEY) || '';
    if (saved && !input.value) input.value = saved;
    const save = () => {
      const value = String(input.value || '').trim();
      if (value) localStorage.setItem(TOKEN_KEY, value);
    };
    input.addEventListener('input', save);
    input.addEventListener('change', save);
    input.addEventListener('blur', save);
  }

  function addVerificationCard() {
    if (document.getElementById('gmailSetupCard')) return;
    const platformCard = document.querySelector('section.card:not(#setupCard)');
    if (!platformCard) return;
    const card = document.createElement('section');
    card.id = 'gmailSetupCard';
    card.className = 'card';
    card.style.borderColor = '#625128';
    card.innerHTML = `
      <div class="title">Email Verification Setup</div>
      <div class="small">Required only for automated account verification. Paste your Google <b>App Password</b> once. It is sent directly to the setup endpoint and installed as a GitHub Actions secret; this page does not save the App Password.</div>
      <div class="label">Gmail App Password</div>
      <input id="gmailAppPasswordInput" type="password" autocomplete="off" placeholder="Paste App Password"/>
      <button id="saveGmailSetupBtn" style="width:100%;margin-top:10px">SAVE VERIFICATION SETUP</button>
      <div id="gmailSetupMessage" class="small" style="margin-top:9px"></div>`;
    platformCard.parentNode.insertBefore(card, platformCard.nextSibling);

    document.getElementById('saveGmailSetupBtn').onclick = async () => {
      const btn = document.getElementById('saveGmailSetupBtn');
      const msg = document.getElementById('gmailSetupMessage');
      const token = localStorage.getItem(TOKEN_KEY) || '';
      const appPassword = String(document.getElementById('gmailAppPasswordInput').value || '').trim();
      if (!token) {
        msg.className = 'small badtext';
        msg.textContent = 'Finish the one-time GitHub authorization first.';
        return;
      }
      if (!appPassword) {
        msg.className = 'small badtext';
        msg.textContent = 'Paste your Gmail App Password first.';
        return;
      }
      btn.disabled = true;
      btn.textContent = 'SAVING…';
      msg.className = 'small';
      msg.textContent = 'Installing verification credentials securely…';
      try {
        const r = await fetch('/api/social-bot-setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token, controlKey: ensureControlKey(), gmailAppPassword: appPassword })
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok || !data.ok) throw new Error(data.message || `Setup failed (${r.status}).`);
        localStorage.setItem(GMAIL_SAVED_KEY, String(Date.now()));
        document.getElementById('gmailAppPasswordInput').value = '';
        msg.className = 'small oktext';
        msg.textContent = '✓ Email verification setup saved.';
        setTimeout(() => { card.style.display = 'none'; }, 900);
      } catch (e) {
        msg.className = 'small badtext';
        msg.textContent = e.message;
      } finally {
        btn.disabled = false;
        btn.textContent = 'SAVE VERIFICATION SETUP';
      }
    };
  }

  function friendlyError(code) {
    const messages = {
      PUBLIC_SOCIAL_PLATFORM_BLOCKED: 'That URL is a blocked public social platform. Use the private/owned test domain this tool is configured for.',
      CHROME_NOT_FOUND_ON_WORKER: 'The remote browser is unavailable on the worker.',
      GMAIL_VERIFICATION_NOT_CONFIGURED: 'Email verification is not configured yet. Complete Email Verification Setup below.',
      VERIFICATION_EMAIL_NOT_CONFIGURED: 'Email verification is not configured yet. Complete Email Verification Setup below.',
      CONNECT_SITE_FIRST: 'Connect the private test site before starting this task.',
      STATE_DECRYPT_FAILED: 'The encrypted worker state does not match the saved key. Re-run one-time authorization.'
    };
    return messages[code] || `Worker error: ${code}`;
  }

  async function refreshHealth() {
    try {
      const r = await nativeFetch(RAW_STATUS + '?phonefix=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) return;
      const s = await r.json();
      const card = document.getElementById('gmailSetupCard');
      if (card) {
        if (s.worker?.emailConfigured) {
          localStorage.removeItem(GMAIL_SAVED_KEY);
          card.style.display = 'none';
        } else {
          const savedAt = Number(localStorage.getItem(GMAIL_SAVED_KEY) || 0);
          const waitingForHeartbeat = savedAt && Date.now() - savedAt < 20 * 60 * 1000;
          card.style.display = waitingForHeartbeat ? 'none' : '';
        }
      }

      if (s.lastRequestStatus === 'failed' && s.lastMessage) {
        const scan = document.getElementById('scanText');
        const pill = document.getElementById('connectPill');
        if (scan) {
          scan.className = 'small badtext';
          scan.textContent = friendlyError(s.lastMessage);
        }
        if (pill) {
          pill.className = 'pill bad';
          pill.textContent = 'ERROR';
        }
      }
    } catch {}
  }

  function init() {
    wireTokenPersistence();
    ensureControlKey();
    addVerificationCard();
    refreshHealth();
    setInterval(refreshHealth, 20000);
  }

  wireTokenPersistence();
  ensureControlKey();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
