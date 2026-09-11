# Social Bot

Phone-first private social-platform testing control center.

## Normal use

Open `/social-bot` in Safari, paste the private/owned test platform URL, tap **CONNECT**, then use the amount boxes and **START** buttons.

The phone is only the control panel. GitHub Actions runs the browser worker remotely. Closing Safari does not stop queued work.

## One-time setup

The Safari page asks for one fine-grained GitHub token for `RubysRealm/RubysRealm` with:

- **Actions: read/write**
- **Secrets: read/write**

The page stores that token locally on the phone as soon as it is pasted. It generates a 32-byte Social Bot encryption key locally and reuses the same key on setup retries. The setup endpoint installs that key into the repository as `SOCIALBOT_KEY` automatically.

For automated Gmail verification, the phone page shows **Email Verification Setup** when the worker reports that Gmail verification is not configured. Paste a Google App Password there once. The App Password is installed as the `SOCIALBOT_GMAIL_APP_PASSWORD` GitHub Actions secret and is not saved by the phone page.

Detailed generated account state, credentials and browser sessions are encrypted before being stored on the `social-bot-state` branch. Aggregate worker/status information is stored separately for the phone dashboard.

## Controls

- **CONNECT** — probes the entered private site, scans the current UI and stores a site profile.
- **Generate Emails / Profiles** — creates correlated synthetic name, username, Gmail plus-alias, DOB, password and interest records.
- **Create Accounts** — queues signup attempts through the visible front-end flow. Optional pacing spreads them over 24 hours, 3 days or 7 days.
- **Discovery Feed Activity** — queues feed browsing/interaction tasks for created test accounts.
- **Specific Video** — queues private-site video visits/interactions, spread over the selected window.
- **Specific Profile Follow** — queues follows to a private-site profile, spread over the selected window.
- **Random Follows** — discovers profile links on the connected private site and queues follow attempts.
- **Fix Failed** — retries failed technical tasks.
- **Pause / Resume / Stop** — controls queued work.

## Boundaries

The worker accepts only URLs on the connected origin for profile/video targets. Known public social-media hosts are blocked. CAPTCHAs and security challenges are reported as failures rather than bypassed.
