(() => {
  const TOKEN_KEY = 'socialbot_gh_token';
  const KEY_KEY = 'socialbot_key';
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
      key = b64u(crypto.getRandomValues(new Uint8Array(32)));
      localStorage.setItem(KEY_KEY, key);
    }
    return key;
  }

  // Make setup retries idempotent. The same phone key is re-installed instead of
  // silently rotating encryption whenever the user retries authorization.
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

  async function refreshHealth() {
    try {
      const r = await nativeFetch(RAW_STATUS + '?phonefix=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) return;
      const s = await r.json();
      const card = document.getElementById('gmailSetupCard');
      if (card && s.worker?.emailConfigured) card.style.display = 'none';
      if (card && !s.worker?.emailConfigured) card.style.display = '';

      // Surface worker failures on the phone page instead of silently returning CONNECT.
      if (s.lastRequestStatus === 'failed' && s.lastMessage) {
        const scan = document.getElementById('scanText');
        const pill = document.getElementById('connectPill');
        if (scan) {
          scan.className = 'small badtext';
          scan.textContent = `Worker error: ${s.lastMessage}`;
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

  // The page elements already exist before the original inline script runs.
  wireTokenPersistence();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
