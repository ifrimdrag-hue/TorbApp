# Infrastructure — VPS Server

> **Maintenance rule:** this file is the single source of truth for server facts.
> Whenever a server question is answered (ownership, permissions, users, services,
> ports, cron entries), record the answer here immediately — future sessions must
> be able to answer these questions from this file without asking.

## Server

| Property | Value |
|---|---|
| Provider | **cyberfolks.ro** (panel login + 2FA in `docs/manuals/server/secrets.local.md`) |
| OS | Ubuntu 24.04.4 LTS (Noble Numbat), kernel `6.8.0-117-generic`, x86_64 (verified 2026-06-15) |
| Hardware | 2 vCPU / 2.8 GB RAM / **0 swap** / 48 GB disk (`/dev/sda1`, ~16% used) |
| IP | 188.241.116.172 |
| SSH port | 2112 (sshd listens here only) |
| SSH user | openclaw |
| Domain | app.robrands.ro (+ www.app.robrands.ro) |
| SSL | Let's Encrypt via Certbot 2.9.0, **ECDSA**, expires **2026-08-23**, auto-renew 30d before (nginx authenticator, `certbot.timer`) |
| VPS-level backups | Done by the hosting provider (full machine) |
| Versions (2026-06-15) | Python 3.12.3 · gunicorn 26.0.0 · nginx 1.24.0 · Node v22.22.2 / npm 10.9.7 · OpenClaw 2026.6.6 |

**Full reproduction manual:** `docs/manuals/server/manual_server.typ` (compiled PDF alongside) —
verbatim systemd units, nginx vhosts, a from-scratch rebuild runbook, and the secrets inventory.
Keep this file and the manual in sync.

### Users & filesystem ownership (verified 2026-06-11)

| Question | Answer |
|---|---|
| Deploy/SSH user (GitHub Actions + manual SSH) | `openclaw` — uid 999, groups: `openclaw`, `www-data` (`sudo` + `docker` removed 2026-06-13 — see OpenClaw security section). Deploy `systemctl restart` works via scoped NOPASSWD sudoers (`torb-deploy`), **not** group membership. |
| Service user (gunicorn `torb-py` + `torb-dev`) | `www-data` — uid 33, groups: `www-data` only |
| Owner of `/var/www/html/torb-py` | `www-data:www-data`, mode 775 (group-writable) |
| Owner of `data/` and `torb.db` | `www-data:www-data`, mode 775 |
| Owner of `data/backups/` | `www-data:www-data`, mode **2775** (setgid — files created by `openclaw` inherit group `www-data`) |
| Why `openclaw` deploys can write the app tree | `openclaw` is in the `www-data` group and dirs are group-writable |

Note: `data/` also contains a stray pre-engine manual backup `torb.db.bak.20260525_010848`
(102 MB, from 2026-05-25) — can be deleted once the new backup system is verified.

### SSH access & deploy keys (verified 2026-06-15)

- **Human admin login:** **key-only** on port 2112 since 2026-06-15 (`PasswordAuthentication no`). A
  personal admin SSH key was added to `~/.ssh/authorized_keys`; the `openclaw` account password is now
  used **only** for the cyberfolks emergency console (not SSH) — stored in
  `docs/manuals/server/secrets.local.md`.
- **`~/.ssh/authorized_keys` (openclaw)** — two authorized keys (verified 2026-06-15):
  1. `github-deploy` — `SHA256:EigIB4gJEujSSi0Hko7rZSCwmpcJmmxo6ctouxqzfaE` = the **live `VPS_SSH_KEY`**
     (GitHub Actions; last seen 2026-06-13).
  2. `vladr-laptop` — `SHA256:rFRS0osjmEEO+xmifuXLbDzYcbR2gOi5Nnojj9/2Ie0` = the **personal admin key**
     added 2026-06-15; this is what enables key-only login now that password auth is off.
- **Cleanup 2026-06-15:** removed a stray literal `paste-public-key-here` line and a **stale** rotated
  deploy key `github-actions-deploy` (`SHA256:5DP0…f2r0`, unused since 2026-05-25). Backups:
  `~/.ssh/authorized_keys.bak.*`. **Follow-up:** delete the orphaned `5DP0` key from GitHub repo
  *Settings → Deploy keys* / *Secrets* if it still exists there.

### Scheduled jobs (cron)

| Job | User | Schedule | Command |
|---|---|---|---|
| Daily DB backup (prod) | `www-data` (installed 2026-06-11) | 02:30 | `cd /var/www/html/torb-py && venv/bin/python etl/backup_db.py backup --tag daily >> logs/backup.log 2>&1` |

Inspect / edit: `sudo -u www-data crontab -l` / `sudo -u www-data crontab -e`.
Job output: `/var/www/html/torb-py/logs/backup.log`.

---

## Environments

### Production

| Property | Value |
|---|---|
| URL | https://app.robrands.ro |
| Path | `/var/www/html/torb-py` |
| Systemd service | `torb-py` |
| Gunicorn bind | `127.0.0.1:5000` |
| Gunicorn workers | 3 |
| Run as | `www-data` |
| venv | `/var/www/html/torb-py/venv` |
| Database | `/var/www/html/torb-py/data/torb.db` |
| Env file | `/var/www/html/torb-py/.env` |
| Logs | `/var/www/html/torb-py/logs/app.log` |
| Deploy trigger | Push to `main` (GitHub Actions) |

### Dev / Test

| Property | Value |
|---|---|
| URL | https://app.robrands.ro:5001 |
| Path | `/var/www/html/torb-py-dev` |
| Systemd service | `torb-dev` |
| Gunicorn bind | `127.0.0.1:5002` |
| Gunicorn workers | 2 |
| Run as | `www-data` |
| venv | `/var/www/html/torb-py-dev/venv` |
| Database | `/var/www/html/torb-py-dev/data/torb.db` (independent copy) |
| Env file | `/var/www/html/torb-py-dev/.env` |
| Logs | `/var/www/html/torb-py-dev/logs/app.log` |
| Deploy trigger | Push to `main` via `deploy_dev` CI job (planned) |

---

## Nginx

Config files:
- `/etc/nginx/sites-available/app.robrands.ro` — production vhost (managed by Certbot)
- `/etc/nginx/sites-available/torb-dev` — dev vhost (port 5001)
- `/etc/nginx/sites-enabled/default` — fallback, proxies to `127.0.0.1:5000`

Routing summary:
```
:80  → 301 to https://app.robrands.ro (Certbot)
:443 → nginx → 127.0.0.1:5000 (prod gunicorn)
:5001 ssl → nginx → 127.0.0.1:5002 (dev gunicorn)
```

SSL certificate: `/etc/letsencrypt/live/app.robrands.ro/`
- `fullchain.pem` / `privkey.pem`
- Shared by both prod and dev nginx blocks

---

## Systemd Services

```bash
sudo systemctl status torb-py      # production
sudo systemctl status torb-dev     # dev/test
sudo systemctl restart torb-py
sudo systemctl restart torb-dev
```

Service files:
- `/etc/systemd/system/torb-py.service`
- `/etc/systemd/system/torb-dev.service`

---

## Firewall (ufw)

Active, default deny incoming. Rules after hardening (2026-06-15, IPv4+IPv6):

| Port | Protocol | Purpose |
|---|---|---|
| 2112 | TCP | SSH (only port sshd listens on) |
| 80 | TCP | HTTP (redirects to HTTPS) |
| 443 | TCP | HTTPS — production |
| 5001 | TCP | HTTPS — dev/test |

> **✅ SECURITY HARDENING 2026-06-15 (RESUME CHECKLIST applied after sudo restore):**
> - ✅ Removed stale `22/tcp` + `8888/tcp` firewall rules (sshd listens on `2112` only).
> - ✅ Disabled Tailscale (`systemctl disable --now tailscaled`) + closed `41641/udp` (was `Logged out`).
> - ✅ sshd `PermitRootLogin prohibit-password` via `/etc/ssh/sshd_config.d/99-torb-hardening.conf`.
> - ✅ `.env` confirmed `640 openclaw:www-data`; no pending security updates; OpenClaw gateway recycled.
> - ✅ fail2ban `[sshd]` active.
> - ✅ `server_tokens off;` applied in `nginx.conf` (reloaded 2026-06-15 — version no longer leaked).
> - ✅ `PasswordAuthentication no` (2026-06-15) — a personal admin SSH key was configured, then
>   password auth disabled; SSH is now **key-only**. Recovery if the key is lost: cyberfolks console
>   (password login still works there — it's a local console, not SSH).

---

## Repository

GitHub: `https://github.com/ifrimdrag-hue/TorbApp`

Git safe directories configured on server:
```bash
git config --global --add safe.directory /var/www/html/torb-py
git config --global --add safe.directory /var/www/html/torb-py-dev
```

---

## CI/CD

Pipeline: `.github/workflows/deploy_VPS.yml`

Current jobs (as of 2026-06-04):
1. `lint` — ruff check
2. `test` — pytest
3. `security` — pip-audit
4. `deploy` → being renamed to `deploy_prd`
5. `smoke-test-vps` → being renamed to `test_prd`

Planned jobs (not yet implemented — see memory `project-dev-env-plan`):
- `deploy_dev` — deploys to `/var/www/html/torb-py-dev`, restarts `torb-dev`
- `test_dev` — smoke tests against `https://app.robrands.ro:5001`
- `approve_prd` — manual gate via GitHub Environment `production`

---

## Database Backups (production only)

| Property | Value |
|---|---|
| Location | `/var/www/html/torb-py/data/backups/` |
| Format | `torb_YYYY-MM-DD_HHMMSS_<tag>.db.gz` (tags: daily, pre-deploy, pre-restore, manual) |
| Retention | 15 days, always keeping the newest 3 regardless of age |
| Daily trigger | cron (www-data), 02:30 — `python etl/backup_db.py backup --tag daily` |
| Pre-deploy trigger | CI `deploy_prd` job, right before migrations |
| Admin UI | `https://app.robrands.ro/admin/db` — list, manual backup, download, guarded restore |
| Engine | SQLite online backup API (safe on a live WAL database) — `app/backup_db.py` |

CLI (from `/var/www/html/torb-py`, venv active):
```bash
python etl/backup_db.py list
python etl/backup_db.py backup --tag manual
python etl/backup_db.py restore torb_2026-06-11_023000_daily.db.gz
```

Restore notes: a pre-restore safety backup of the current state is created automatically;
migrations re-run after restore (older backups get upgraded to current schema); restart
the service afterwards (`sudo systemctl restart torb-py`) so all gunicorn workers drop
their in-memory caches. Dev (`torb-py-dev`) has no scheduled backups by design.

---

## Email / SMTP (password-reset)

Password-reset emails are sent via SMTP — Python `smtplib` + STARTTLS, sender `_smtp_send` in
`app/blueprints/auth.py`. Configured **only** by env vars in `.env`:

| Var | Purpose |
|---|---|
| `SMTP_HOST` | SMTP server host. If unset, email is disabled and reset **degrades gracefully** (UI shows "reset by email not configured"). |
| `SMTP_PORT` | default `587` (STARTTLS) |
| `SMTP_USER` / `SMTP_PASSWORD` | auth (login skipped if empty) |
| `SMTP_FROM` | From header (defaults to `SMTP_USER`) |

> **CI-managed since 2026-06-15:** `SMTP_USER` + `SMTP_PASSWORD` are now injected by the deploy
> workflow from GitHub Actions Secrets (both `deploy_dev` and `deploy_prd`). The non-secret
> `SMTP_HOST`/`SMTP_PORT`/`SMTP_FROM` live in `.env.example`; the deploy does **not** rewrite them, so
> they must remain present in the server `.env` (they are). **⚠️ The GitHub repo must have `SMTP_USER`
> and `SMTP_PASSWORD` secrets set** — otherwise the next deploy writes empty values and email breaks.

Current config (2026-06-15): **Gmail** — `smtp.gmail.com:587` STARTTLS, auth user
`vlad.rosioru@gmail.com` with a **Gmail App Password** (not the account password), From
`Torb Logistic <office@tobra.ro>`. App password stored in `docs/manuals/server/secrets.local.md` (§8).
Note: tied to a personal Gmail — consider a dedicated mailbox / transactional provider long-term.

## Pending maintenance & open items

- **🔁 Reboot pending (schedule a brief maintenance window).** Login banner shows
  `*** System restart required ***` (kernel update `6.8.0-117` applied) plus ~17 updates available
  (4 ESM security). A reboot also: applies the new kernel, and **fully recycles the OpenClaw gateway
  user session** — closing the long-standing "stale `docker`/`sudo` supplementary groups on the live
  process" residual item. Plan: announce downtime, `sudo apt update && sudo apt full-upgrade`, then
  `sudo reboot`; afterwards verify both apps (`/healthz` on prod + dev) and the OpenClaw widget.
- **GitHub deploy-key cleanup.** Delete the orphaned `github-actions-deploy` (`SHA256:5DP0…f2r0`) from
  repo *Settings → Deploy keys* / *Secrets* (already removed from server `authorized_keys` 2026-06-15).
- **SMTP secrets.** Ensure `SMTP_USER` + `SMTP_PASSWORD` exist in GitHub Actions Secrets (the deploy
  now injects them — empty secrets would break password-reset email).
- **Add swap** — box has 0 swap (2 vCPU / 2.8 GB). See manual ch. "Stare curentă".
- **Encrypt the secrets companion** (`secrets.local.md` is plaintext) or move to a password vault.
- **CSP header** still deferred (audit inline scripts + CDN assets first).
- **OpenClaw under a dedicated low-priv user** (long-term) — currently shares the `openclaw` deploy/admin account.

## Useful One-Liners

```bash
# Tail logs
sudo tail -f /var/www/html/torb-py/logs/app.log
sudo tail -f /var/www/html/torb-py-dev/logs/app.log

# Smoke test prod
curl -s -o /dev/null -w "%{http_code}\n" https://app.robrands.ro/healthz

# Smoke test dev
curl -s -o /dev/null -w "%{http_code}\n" https://app.robrands.ro:5001/healthz

# Check nginx config
sudo nginx -t

# Reload nginx (no downtime)
sudo systemctl reload nginx
```

---

## OpenClaw gateway (agent integration) — state as of 2026-06-13

OpenClaw (Node; auto-updated to **v2026.6.6** mid-setup on 2026-06-13) runs as a
**user-linger** systemd service under the `openclaw` account — **not** system scope.
Manage it as that user with the runtime dir exported:

```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)      # run as the openclaw user
systemctl --user status|restart openclaw-gateway.service
```

| Property | Value |
|---|---|
| Service | `openclaw-gateway.service` (user unit, `~/.config/systemd/user/`) |
| ExecStart | `node ~/.local/lib/node_modules/openclaw/dist/index.js gateway --port 18789` |
| Listens | `127.0.0.1:18789` (gateway, WS at `/ws`) + `127.0.0.1:18791` (browser control) |
| Config | `~/.openclaw/openclaw.json` (JSON5) |
| Auth | gateway token **+** per-device roles/scopes (see notes below) |
| Provider | OpenRouter, model `openrouter/free` (free-only router; changed from `openrouter/auto` 2026-06-13) |

**Fixes applied 2026-06-13 (gateway was dead before this):**
1. Config `openclaw.json` was truncated/corrupt (JSON5 EOF at line 56) → restored from
   `~/.openclaw/openclaw.json.last-good`.
2. The unit's ExecStart had `--trusted-proxy 127.0.0.1`, **unsupported in this version**
   → removed (gateway exited 1 on every start).
3. Auto-updated to **2026.6.6** mid-setup (v4 control protocol + per-agent auth store).
   Needed a gateway restart to clear a v3/v4 "protocol mismatch" in the dashboard.
4. **Device scopes:** the old `operator` device (paired under 2026.4.29) was stuck at
   `read`+`pairing`; agent turns need `write`, and piecemeal CLI approval races on
   ephemeral request ids (`unknown requestId`). Fixed by approving the pending scope
   upgrade in the **dashboard** (Nodes → Devices) once an admin-scoped device existed.
   New local pairings under 2026.6.6 auto-get full scopes.
5. **Provider auth is per-agent** (`~/.openclaw/agents/main/agent/openclaw-agent.sqlite`).
   Set via `openclaw models auth login --provider openrouter` (OAuth). **Restart the
   gateway afterward** so it reloads the key, else turns fail "No API key found".

Verified working end-to-end 2026-06-13: the full app path
`www-data → sudo -u openclaw → wrapper → openclaw agent → gateway → OpenRouter`
returns a real reply in ~4s. Output shape: `{runId, status:"ok", result:{payloads:[{text}], meta}}`.
Agent `main` is **out of BOOTSTRAP** and replies normally (no identity-onboarding script).

**Free-only models (2026-06-13):** model switched `openrouter/auto` → `openrouter/free` in
`~/.openclaw/openclaw.json` (default + alias + configured-models entry) to cap cost at free tier.
Verified end-to-end: agent turn returns `status:ok`, `winnerModel:openrouter/free`, tool calls
succeed (`session_status`, 0 failures) — free router picks a tool-capable model. Trade-offs: slower
(~15s vs ~4s) and lower output quality. Revert: restore `~/.openclaw/openclaw.json.bak.<ts>` +
`systemctl --user restart openclaw-gateway.service`. If turns later fail on tool schemas, pin a
specific free model (e.g. `meta-llama/llama-3.3-70b-instruct:free`).

**Flask integration (CLI, not WebSocket):** route `/admin/openclaw-ask` in `app/app.py`
shells out to `sudo -n -u openclaw <wrapper> <session_id> <prompt>`, parses
`result.payloads[0].text`, returns `{reply}`. Chosen over a raw WS because the gateway
uses a challenge-response + device-scope handshake that's impractical to reimplement, and
the CLI always matches the installed version. `www-data` (gunicorn) can't read
`/home/openclaw/.openclaw`, hence the `sudo -u openclaw` hop. Flask no longer uses
`OPENCLAW_TOKEN` / `OPENCLAW_WS_URL` (those can be dropped from `.env`/secrets); optional
overrides are `OPENCLAW_ASK_BIN` and `OPENCLAW_TIMEOUT`.

VPS glue — **installed & verified 2026-06-13** (the `www-data → openclaw` test returns `status: ok`):
- Wrapper `/usr/local/bin/torb-openclaw-ask` (root-owned, mode 0755):
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  export HOME=/home/openclaw
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
  export PATH="/home/openclaw/.local/bin:/usr/bin:/bin"
  exec openclaw agent --agent main --session-id "${1:?}" -m "${2:?}" --json
  ```
- Sudoers `/etc/sudoers.d/torb-openclaw` (mode 0440, `visudo -cf` parses OK):
  ```
  www-data ALL=(openclaw) NOPASSWD: /usr/local/bin/torb-openclaw-ask
  ```
- `torb-py` confirmed **without** `NoNewPrivileges`, so the `sudo` setuid hop works. If a
  future hardening pass adds `NoNewPrivileges=true`, sudo breaks — remove it, `daemon-reload`,
  restart.

**Remaining (optional):**
- (a) ✅ **Resolved 2026-06-13** — exec is now `deny-all` (see security section below); the agent
  cannot run server commands at all. Chat-only by design. To later allow read-only server prompts
  ("check RAM / count DB rows"), switch to `exec-policy preset cautious` + a tight allowlist
  (`openclaw approvals allowlist add`) rather than reverting to `deny-all`/`full`.
- (b) ✅ **Done 2026-06-13** — removed the two legacy nginx `location /admin/openclaw-ws`
  blocks (`app.robrands.ro` + `default`). `/admin/openclaw-ws/` now returns 302→login (served
  by Flask) instead of proxying to the gateway, closing the auth-bypass back-door. Backups:
  `*.bak.<date>` in `/etc/nginx/sites-available/`.
- (c) Add a swapfile — box is 2 vCPU / 2.8 GB / **0 swap**.
- (d) The app route `/admin/openclaw-ask` ships on the next push (commits `5d3fcc1`, `5bc162a`).

### ✅ SECURITY — RESOLVED 2026-06-13 (locked down; was OPEN since 2026-06-13)

**Question asked:** "is everything secure, including what OpenClaw can execute on the server?"

**Original verdict:** Internet-facing surface was fine (admin-only + CSRF route, gateway
loopback-only, nginx back-door removed). But **what the agent could execute was NOT secure** —
`tools.exec security=full, ask=off`, empty allowlist (runs any shell command, no prompt), while
`openclaw` was in the `sudo` + `docker` (root-equivalent) groups. Any Flask admin, or anyone with
code-exec as `www-data`, could prompt the agent into arbitrary commands and **escalate to root**.

**Lockdown applied (all verified):**
1. **Exec disabled.** `openclaw exec-policy preset deny-all` → host approvals
   `~/.openclaw/exec-approvals.json` defaults now `security=deny, ask=off, askFallback=deny`.
   Gateway restarted to load it. Effective policy confirmed `security=deny`. The agent's `exec`
   tool is still offered in-schema but the host policy denies it at execution time. (Rollback:
   `openclaw approvals set --file ~/.openclaw/exec-approvals.json.bak.20260613` + gateway restart.)
2. **Root-equivalent groups dropped.** `sudo gpasswd -d openclaw docker` (zero containers, group
   unused) + `sudo gpasswd -d openclaw sudo`. `openclaw` groups are now `openclaw, www-data` only;
   the general `(ALL:ALL) ALL` sudo grant is gone (confirmed in a fresh login session).
3. **Deploys still work** — the `torb-deploy` sudoers file already grants `openclaw` NOPASSWD on
   `/bin/systemctl restart torb-py` and `/usr/bin/systemctl restart torb-dev` directly (user-based,
   not group-based). Deploys are non-interactive and never used the password-gated `%sudo` grant.
   Verified post-change: `sudo -n -l /bin/systemctl restart torb-py` and `…torb-dev` both permitted.
4. **Widget chat unaffected** — `www-data → wrapper → agent` smoke test returns `status: ok` after
   the policy change + gateway restart (~3s).

**Residual / next maintenance window (low priority):**
- The **running gateway process** still holds the old `docker`/`sudo` supplementary groups until
  its user session is recycled (`sudo loginctl terminate-user openclaw`, or a reboot). Inert while
  exec is `deny` (no way to invoke docker without exec), but recycle for full hygiene.
- **Long-term:** run the gateway/agent as a dedicated low-priv user, separate from the deploy user.

---

## Full security audit — 2026-06-13

Read-only audit across app + host after the OpenClaw lockdown. Posture is sound; items below.

**Verified solid:** fail2ban active (`[sshd]` jail on); ufw active; gunicorn (`:5000`/`:5002`) +
agent gateway (`:18789`) are **loopback-only**;
`~/.openclaw` is `700`, agent key sqlite `600`, nothing world-readable; unattended security
upgrades on; SQLi not exposed (bound params; dynamic `{sets}` = whitelisted columns); CSRF
app-wide; passwords pbkdf2.

**Fixed in code/CI (commit `51e6b4c`):**
- `ProxyFix(x_for, x_proto)` in `app/app.py` — nginx sets `X-Forwarded-For`/`-Proto` but Flask
  saw `127.0.0.1`, so the login rate limiter was effectively global and audit IPs were useless.
- Security headers via `after_request`: `X-Content-Type-Options`, `X-Frame-Options=SAMEORIGIN`,
  `Referrer-Policy`, HSTS. **CSP deliberately deferred** (inline scripts + CDN assets need an audit).
- `deploy_VPS.yml` (prod+dev): inject `SESSION_COOKIE_SECURE=1`; `chgrp www-data` + `chmod 640`
  on `.env` after every write (the `grep|mv` rewrites otherwise reset it to world-readable `664`).

**Fixed on server 2026-06-13:** `.env` was `664 openclaw:openclaw` (secrets world-readable) →
`640 openclaw:www-data` on prod + dev. *(Confirm with `ls -l .env`.)*

> **⚠️ LESSON 2026-06-13:** dropping `openclaw` from the `sudo` group locked the human admin
> out of root — `openclaw` is the *only* admin account and there is no separate root password.
> The real escalation hole was the **`docker`** group (passwordless root); `sudo` is
> password-gated and the non-interactive agent could never use it. **Keep `openclaw` in `sudo`.**
> Recovery requires the provider console (`usermod -aG sudo openclaw`). Don't remove the sole
> admin's sudo again.

**UPDATE 2026-06-15:** ✅ **sudo restored** — `openclaw` is back in the `sudo` group (provider
ticket resolved); `sudo -v` works. The RESUME CHECKLIST below is **unblocked**. Block B was run
and surfaced new findings (see Firewall section: un-hardened sshd, stale 22/8888 rules, dormant
Tailscale) — these are folded into the checklist. `ANTHROPIC_API_KEY` confirmed **still in use** by
the in-app Claude features (ai.py, post/campaign generators, ai_suggestions, auto_posts) — do **not**
remove it; the OpenRouter switch only affects the OpenClaw gateway.

**PRIOR STATE (2026-06-13, Sat):** code/CI fixes **pushed & deployed to prod** (ProxyFix,
security headers, `SESSION_COOKIE_SECURE=1`, `.env` 640); `.env` perms fixed on prod + dev and
login verified on dev before prod approval. Human admin was **locked out of root** — `openclaw`
had no general sudo and there is no separate root account/password. Provider ticket was pending to
run `usermod -aG sudo openclaw` from the console. Deploys/app were unaffected (verified).

### RESUME CHECKLIST — ✅ FULLY APPLIED 2026-06-15 (kept for reference / rebuild)

> All steps done. Step 2 completed in full: a personal admin SSH key was configured and
> `PasswordAuthentication no` applied — SSH is now key-only (see SSH access & Firewall sections above).

```bash
# 1. Confirm recovery
id openclaw                 # expect: ...,27(sudo),33(www-data)
sudo -v                     # should succeed (no "not allowed")

# 2. SSH hardening
sshd -T | grep -Ei 'permitrootlogin|passwordauthentication|pubkeyauthentication'
sudo tee /etc/ssh/sshd_config.d/99-torb-hardening.conf >/dev/null <<'EOF'
PermitRootLogin prohibit-password
# PasswordAuthentication no   # uncomment ONLY after confirming key login works for you
EOF
sudo sshd -t && sudo systemctl reload ssh

# 3. nginx version leak — add `server_tokens off;` inside http{} of /etc/nginx/nginx.conf, then:
sudo nginx -t && sudo systemctl reload nginx

# 4. Recycle the OpenClaw gateway session (drop stale docker/sudo groups from the live process)
sudo loginctl terminate-user openclaw    # linger restarts the gateway
sleep 5                                   # then verify gateway is up + widget chat answers

# 5. Firewall — remove stale SSH rules (sshd listens on 2112 only; 22 + 8888 are dead)
sudo ufw status verbose
sudo ufw delete allow 22/tcp
sudo ufw delete allow 8888/tcp
sudo fail2ban-client status sshd          # confirm maxretry/bantime

# 6. Tailscale — installed but Logged out + 41641/udp open. Pick ONE:
#    (a) if NOT needed:
sudo systemctl disable --now tailscaled
sudo ufw delete allow 41641/udp
#    (b) if needed: `sudo tailscale up`, then document the tailnet in secrets.local.md

# 7. Cleanup (optional)
ls -l /var/www/html/torb-py/.env                      # confirm 640 openclaw:www-data
sudo rm /etc/nginx/sites-available/*.bak.2026-06-13   # leftover clutter
apt-get -s upgrade | grep -i security                  # any pending security updates
```

**Notes:** keep `PasswordAuthentication no` commented until `sshd -T` + a test key-login confirm
you won't re-lock yourself. Dev app (`:5001`) internet-exposed (separate DB, same auth) — accepted.

**Long-term (separate project, not urgent):** run the OpenClaw gateway/agent as a dedicated
low-privilege user, separate from the `openclaw` deploy/admin account — removes the shared-identity
root cause behind both the exec risk and this lockout.
