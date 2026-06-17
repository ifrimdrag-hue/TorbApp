# Infrastructure — VPS Server

> **Maintenance rule:** this file is the single source of truth for **current** server facts.
> Whenever a server question is answered (ownership, permissions, users, services, ports, cron
> entries), record the answer here immediately — future sessions must be able to answer these
> questions from this file without asking.
>
> **Dated changes, resolved security items, and applied checklists live in
> `context/infrastructure_history.md`** — move narrative there once an item is done; keep this file
> lean (current state + pending work only).
>
> ⛔ **Do not open `infrastructure_history.md` automatically.** It is a write-mostly archive — read it
> **only** when explicitly investigating a past change. Reading this file (`infrastructure.md`) must
> **not** trigger loading the history file.

## Server

| Property | Value |
|---|---|
| Provider | **cyberfolks.ro** (panel login + 2FA in the KeePassXC vault `torb-secrets.kdbx`) |
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

### Users & filesystem ownership

| Question | Answer |
|---|---|
| Deploy/SSH user (GitHub Actions + manual SSH) | `openclaw` — uid 999, groups: `sudo`, `openclaw`, `www-data`. Deploy `systemctl restart` works via scoped NOPASSWD sudoers (`torb-deploy`), **not** group membership. |
| Service user (gunicorn `torb-py` + `torb-dev`) | `www-data` — uid 33, groups: `www-data` only |
| Owner of `/var/www/html/torb-py` | `www-data:www-data`, mode 775 (group-writable) |
| Owner of `data/` and `torb.db` | `www-data:www-data`, mode 775 |
| Owner of `data/backups/` | `www-data:www-data`, mode **2775** (setgid — files created by `openclaw` inherit group `www-data`) |
| Why `openclaw` deploys can write the app tree | `openclaw` is in the `www-data` group and dirs are group-writable |

Note: `data/` also contains a stray pre-engine manual backup `torb.db.bak.20260525_010848`
(102 MB, from 2026-05-25) — can be deleted once the new backup system is verified.

### SSH access & deploy keys

- **Human admin login:** **key-only** on port 2112 (`PasswordAuthentication no`). The `openclaw`
  account password is used **only** for the cyberfolks emergency console (not SSH) — stored in
  the KeePassXC vault `torb-secrets.kdbx`.
- **`~/.ssh/authorized_keys` (openclaw)** — two authorized keys:
  1. `github-deploy` — `SHA256:EigIB4gJEujSSi0Hko7rZSCwmpcJmmxo6ctouxqzfaE` = the **live `VPS_SSH_KEY`**
     (GitHub Actions).
  2. `vladr-laptop` — `SHA256:rFRS0osjmEEO+xmifuXLbDzYcbR2gOi5Nnojj9/2Ie0` = the **personal admin key**;
     this is what enables key-only login.

### Scheduled jobs (cron)

| Job | User | Schedule | Command |
|---|---|---|---|
| Daily DB backup (prod) | `www-data` | 02:30 | `cd /var/www/html/torb-py && venv/bin/python etl/backup_db.py backup --tag daily >> logs/backup.log 2>&1` |

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

`server_tokens off;` is set in `nginx.conf` (version not leaked).

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

Active, default deny incoming. Current rules (IPv4+IPv6):

| Port | Protocol | Purpose |
|---|---|---|
| 2112 | TCP | SSH (only port sshd listens on) |
| 80 | TCP | HTTP (redirects to HTTPS) |
| 443 | TCP | HTTPS — production |
| 5001 | TCP | HTTPS — dev/test |

SSH is key-only (`PasswordAuthentication no`); `PermitRootLogin prohibit-password`; fail2ban
`[sshd]` jail active. Recovery if the key is lost: cyberfolks console (local console, not SSH).

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

> **CI-managed:** `SMTP_USER` + `SMTP_PASSWORD` are injected by the deploy workflow from GitHub
> Actions Secrets (both `deploy_dev` and `deploy_prd`). The non-secret `SMTP_HOST`/`SMTP_PORT`/
> `SMTP_FROM` live in `.env.example`; the deploy does **not** rewrite them, so they must remain
> present in the server `.env` (they are). **⚠️ The GitHub repo must have `SMTP_USER` and
> `SMTP_PASSWORD` secrets set** — otherwise the next deploy writes empty values and email breaks.

Current config: **Gmail** — `smtp.gmail.com:587` STARTTLS, auth user `vlad.rosioru@gmail.com` with a
**Gmail App Password** (not the account password), From `Torb Logistic <office@tobra.ro>`. App
password stored in the KeePassXC vault `torb-secrets.kdbx` (entry "SMTP — Gmail App Password"). Note: tied to a personal Gmail —
consider a dedicated mailbox / transactional provider long-term.

---

## OpenClaw gateway (agent integration)

OpenClaw (Node, **v2026.6.6**) runs as a **user-linger** systemd service under the `openclaw`
account — **not** system scope. Manage it as that user with the runtime dir exported:

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
| Auth | gateway token **+** per-device roles/scopes |
| Provider | OpenRouter, model `openrouter/free` (free-only router) |
| Exec policy | `deny-all` — agent **cannot** run server commands (chat-only by design) |

**Flask integration (CLI, not WebSocket):** route `/admin/openclaw-ask` in `app/app.py` shells out
to `sudo -n -u openclaw <wrapper> <session_id> <prompt>`, parses `result.payloads[0].text`, returns
`{reply}`. Chosen over a raw WS because the gateway uses a challenge-response + device-scope
handshake that's impractical to reimplement, and the CLI always matches the installed version.
`www-data` (gunicorn) can't read `/home/openclaw/.openclaw`, hence the `sudo -u openclaw` hop. Flask
does **not** use `OPENCLAW_TOKEN` / `OPENCLAW_WS_URL` — the stale `OPENCLAW_TOKEN` GitHub Actions
secret was deleted 2026-06-17 (referenced in neither code nor the deploy workflow). Optional overrides
are `OPENCLAW_ASK_BIN` and `OPENCLAW_TIMEOUT`.

VPS glue:
- Wrapper `/usr/local/bin/torb-openclaw-ask` (root-owned, mode 0755):
  ```bash
  #!/usr/bin/env bash
  set -euo pipefail
  export HOME=/home/openclaw
  export XDG_RUNTIME_DIR="/run/user/$(id -u)"
  export PATH="/home/openclaw/.local/bin:/usr/bin:/bin"
  exec openclaw agent --agent main --session-id "${1:?}" -m "${2:?}" --json
  ```
- Sudoers `/etc/sudoers.d/torb-openclaw` (mode 0440):
  ```
  www-data ALL=(openclaw) NOPASSWD: /usr/local/bin/torb-openclaw-ask
  ```
- `torb-py` confirmed **without** `NoNewPrivileges`, so the `sudo` setuid hop works. If a future
  hardening pass adds `NoNewPrivileges=true`, sudo breaks — remove it, `daemon-reload`, restart.

> Setup history, fixes, and the security lockdown narrative are in `context/infrastructure_history.md`
> (load-on-demand archive — only open it if investigating a past change).

---

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

## Pending maintenance & open items

- **🔁 Reboot pending (schedule a brief maintenance window).** Login banner shows
  `*** System restart required ***` (kernel update `6.8.0-117` applied) plus ~17 updates available
  (4 ESM security). A reboot also **fully recycles the OpenClaw gateway user session** — closing the
  long-standing "stale `docker`/`sudo` supplementary groups on the live process" residual item. Plan:
  announce downtime, `sudo apt update && sudo apt full-upgrade`, then `sudo reboot`; afterwards verify
  both apps (`/healthz` on prod + dev) and the OpenClaw widget.
- **Add swap** — box has 0 swap (2 vCPU / 2.8 GB). See manual ch. "Stare curentă".
- ✅ **Secrets vault (done 2026-06-17).** Plaintext `secrets.local.md` migrated into the KeePassXC
  vault `C:\Users\rosio\Vault\torb-secrets.kdbx` (AES-256 + Argon2id, master passphrase held only by
  the owner) and the plaintext securely deleted. *Residual:* the laptop SSD makes overwrite-delete
  non-guaranteed — full-disk encryption (BitLocker) is the real at-rest protection; confirm it's on.
  *Follow-up:* the Typst server manual (`manual_server.typ`, ch. 9) still describes the old
  `secrets.local.md` file — update + recompile.
- **CSP header** — ✅ pragmatic policy shipped (`app/app.py` `_security_headers`): `default-src 'self'`
  with `'unsafe-inline'` for script/style (all assets are same-origin; no CDN). Blocks external script/
  style/frame injection + exfiltration. **Follow-up (own task):** strict nonce-based CSP — requires
  refactoring 17 templates (99 inline event handlers → `addEventListener`, ~25 inline `<script>` blocks
  externalized/nonce'd, inline `style=` → CSS classes).
- **OpenClaw under a dedicated low-priv user** (long-term) — currently shares the `openclaw`
  deploy/admin account; removes the shared-identity root cause behind both the exec risk and the
  earlier sudo lockout.
