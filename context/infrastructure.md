# Infrastructure — VPS Server

> **Maintenance rule:** this file is the single source of truth for server facts.
> Whenever a server question is answered (ownership, permissions, users, services,
> ports, cron entries), record the answer here immediately — future sessions must
> be able to answer these questions from this file without asking.

## Server

| Property | Value |
|---|---|
| Provider | VPS (Linux) |
| IP | 188.241.116.172 |
| SSH port | 2112 |
| SSH user | openclaw |
| Domain | app.robrands.ro |
| SSL | Let's Encrypt via Certbot (auto-renewal) |
| VPS-level backups | Done by the hosting provider (full machine) |

### Users & filesystem ownership (verified 2026-06-11)

| Question | Answer |
|---|---|
| Deploy/SSH user (GitHub Actions + manual SSH) | `openclaw` — uid 999, groups: `openclaw`, `sudo`, `www-data`, `docker` |
| Service user (gunicorn `torb-py` + `torb-dev`) | `www-data` — uid 33, groups: `www-data` only |
| Owner of `/var/www/html/torb-py` | `www-data:www-data`, mode 775 (group-writable) |
| Owner of `data/` and `torb.db` | `www-data:www-data`, mode 775 |
| Owner of `data/backups/` | `www-data:www-data`, mode **2775** (setgid — files created by `openclaw` inherit group `www-data`) |
| Why `openclaw` deploys can write the app tree | `openclaw` is in the `www-data` group and dirs are group-writable |

Note: `data/` also contains a stray pre-engine manual backup `torb.db.bak.20260525_010848`
(102 MB, from 2026-05-25) — can be deleted once the new backup system is verified.

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

| Port | Protocol | Purpose |
|---|---|---|
| 22 / 2112 | TCP | SSH |
| 80 | TCP | HTTP (redirects to HTTPS) |
| 443 | TCP | HTTPS — production |
| 5001 | TCP | HTTPS — dev/test |

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
| Provider | OpenRouter, model `openrouter/auto` |

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
- (a) Set the exec allowlist (`openclaw approvals allowlist`) before letting the agent run
  server commands. Chat works without it, but prompts like "check RAM / count DB rows" need it.
- (b) ✅ **Done 2026-06-13** — removed the two legacy nginx `location /admin/openclaw-ws`
  blocks (`app.robrands.ro` + `default`). `/admin/openclaw-ws/` now returns 302→login (served
  by Flask) instead of proxying to the gateway, closing the auth-bypass back-door. Backups:
  `*.bak.<date>` in `/etc/nginx/sites-available/`.
- (c) Add a swapfile — box is 2 vCPU / 2.8 GB / **0 swap**.
- (d) The app route `/admin/openclaw-ask` ships on the next push (commits `5d3fcc1`, `5bc162a`).
