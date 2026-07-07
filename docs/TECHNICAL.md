# Technical Documentation

Strictly technical reference: data layer, input files, deploy pipeline, VPS infrastructure, encoding rules, and Typst manual rules. Consolidated 2026-07-02 from `.claude/project_knowledge.md` and `context/infrastructure.md` + `context/reference_data_files.md`. Update in place when facts change — this file is the single source for these notes.

Setup, run, and project-structure basics are in `README.md`; directory placement rules are in `CLAUDE.md`. Implemented feature logic (bonus, virtual brands, stock sync, forecast) is in `docs/BUSINESS_LOGIC.md`. Open issues live in `docs/BACKLOG.md`.

---

## Data — SQLite database & Excel

`data/torb.db` — 131,898 transaction rows, 2024-01-03 → 2026-03-31.
Main table: `tranzactii` (31 columns). Useful views: `v_vanzari_an_furnizor`, `v_vanzari_luna_agent`, `v_vanzari_luna_client`, `v_top_sku`, `v_clienti`.
To rebuild from source Excel: `python etl/update_data.py` — see **Rebuild pipeline** below. (`etl/import_to_sqlite.py` is a legacy one-shot Baza-sheet loader, kept for reference only.)
Cost table: `corr_vanzari_tobra` — Torb→Tobra invoice lines (true acquisition cost),
diverted at ERP import; consumed by the Auchan-import cost override
(`docs/BUSINESS_LOGIC.md` §3, migration 0013).

Forecast tables live here too — see `app/forecast/README.md`. The `forecast_config`
key/value table (migration 0017) holds the tunable parameters of the client × article
forecast model — window, seasonality gate/caps, delisting threshold, safety coefficient,
coverage — read via `app/forecast/config.py` and edited on `/forecast/setari`
(`docs/BUSINESS_LOGIC.md` §7.1).

Correction/lookup tables use a `corr_` prefix. `corr_leonex_cod_mapping`
(migration 0014) maps Leonex supplier article codes (`MK…`) to Torb internal
codes (`cod_mare`, "Cod TORB"); consumed by `etl/import_comenzi_tranzit_leonex.py`
so imported order lines resolve to the correct Torb product
(`docs/BUSINESS_LOGIC.md` §8).

Receivables snapshot: `solduri_neincasate` (migration 0021) — one row per open ERP
document (invoice/advance) from the consolidated "solduri neîncasate" report,
**replace-loaded** by `etl/import_solduri_neincasate.py` (each import truncates + reinserts,
stamping `data_raport` = upload date). Outstanding = `sumdeincas` (may be negative for
advances/credit notes); the due date is **derived on read** as `datadl + term_pl_cl`, never
taken from the file's `scadenta` column (which only holds the term in days). Read via
`app/queries/solduri.py`, shown on `/solduri-neincasate`. Aging bucket rules:
`docs/BUSINESS_LOGIC.md` §Solduri neîncasate.

Pricing-module tables (migrations 0022–0027): `produse_logistica` (1:1 dims/CBM/weights),
`produse_media` (photos: local `path` under `app/static/product_images/` — created at
runtime, files never committed — and/or `url_sursa`),
`coduri_client_articol` (per-client internal codes), `pricing_config` (margin thresholds,
gama-scoped), `clienti_pricing` (listing template + prospect clients `PROSPECT-<n>`),
`propuneri_pret`/`_linii` (saved simulations), `produse.potential` flag (0027).
Migration **0024 is a data seed** — `migrations/seed/0024_pricing_seed.json` carries the
locally-imported pricing rows to dev/prod because the source Excels
(`Date pricinng&Logistica&Ofertare/`, gitignored) exist only on the owner's Mac and there
is no SSH path; INSERT OR IGNORE, skipped when `produse` is empty (test DBs). CAUTION:
`.gitignore`'s `data/` rule matches at any depth — never put committed files in a
directory named `data/` (that's why the seed lives in `migrations/seed/`).
One-off import script: `etl/import_pricing_f0.py` (+`--seed-conditii`); ad-hoc supplier
price offers are imported at runtime via `/preturi/import-oferta`
(`app/supplier_offer.py`, xls/xlsx, letter-mapped columns → potential articles + landing).
Domain rules: `docs/BUSINESS_LOGIC.md` §10.

P&L-module tables (migration 0028, relocated from the former standalone `pnl_app`):
`pnl_balante_raw` (raw trial-balance rows per `entitate`/`an`/`luna`/`cont`, unique on that
tuple with `ON CONFLICT REPLACE`), `pnl_mapping_conturi` (account → P&L line + sign, **seeded**
33 rows), `pnl_config` (per-line alarm thresholds, **seeded** 9 rows), `pnl_import_log` (import
audit). Entities: `torb`, `tobra`, `grup` (= torb+tobra). Monthly amount is the `rulcd` delta
vs. the prior month. Data loads at runtime by uploading Romanian `.xls` trial balances via
`/pnl/import` (folder scan or single upload; `app/pnl_import.py`, host `xlrd`). Compute:
`app/pnl_logic.py`; reads: `app/queries/pnl.py`; styled Excel (3 entity sheets + KPI):
`build_pnl_xlsx` in `app/exports/excel_export.py`. Routes under `/pnl/*` (`app/blueprints/pnl.py`),
folder config `pnl_torb_folder`/`pnl_tobra_folder` in `app/config.py`.

Migrations are versioned in `migrations/` (`NNNN_YYYYMMDD_description.py`), applied automatically on Flask startup and explicitly in CI before service restart. `schema_version` table tracks applied versions; the runner is idempotent.

### Rebuild pipeline (`etl/rebuild_db.py`)

**What** — `rebuild_db.main()` is a *partial* rebuild, not a full wipe:
1. Backs up `torb.db` (`.bak.<ts>`, keeps 3), then drops & recreates **only** `tranzactii`, `stoc`, and the 6 views. All config/correction tables (`corr_vanzari_tobra`, `produse`, `preturi_vanzare`, `conditii_comerciale`, KPI/echipă tables, `corr_leonex_cod_mapping`, …) are preserved — `CREATE IF NOT EXISTS`, and seeds use `INSERT OR IGNORE`.
2. Re-imports in order: Vânzări ERP → Tobra/Auchan cost override → Profi→Mega merge → stoc → config tables + seeds → echipă+KPI → comenzi în tranzit → gama assignment + stock reconciliation.

So a rebuild refreshes sales/stock from the current Excel sources while keeping manually-maintained config and the accumulated `corr_vanzari_tobra` cost history.

**Post-rebuild — stock-snapshot capture (forecast OOS history):** `python etl/snapshot_stoc.py` copies the latest `stoc` snapshot into `stock_snapshot` (idempotent per date). `stock_snapshot` is *not* in the partial-rebuild drop set, so it accrues day-over-day history for the forecast out-of-stock correction (level-2). Not yet wired into `rebuild_db.main()` — run it after each rebuild (or schedule it) until it is.

**When** — three entry points, all reaching the same code:
- `python etl/update_data.py` — CLI wrapper; auto-detects the latest `Vanzari*.xlsx` (also accepts `--vanzari <file>` / `--folder <name>`).
- `python etl/rebuild_db.py [--vanzari <file>]` — direct CLI.
- `POST /api/actualizare-date` → spawns `update_data.py` in a background thread (`app/blueprints/forecast.py`). **Note:** this endpoint is currently **not wired to any UI button**. The only reachable data-update UI is the `/actualizare` page, whose drag-and-drop zones each run a *single* import script (e.g. `import_vanzari_erp.py`) — **not** the full rebuild.

**Reading Excel files** — use `openpyxl` with `read_only=True` for large files:
```python
import openpyxl
wb = openpyxl.load_workbook('file.xlsx', data_only=True, read_only=True)
```

The data-model semantics (what `tranzactii` columns mean, domain vocabulary, gotchas like Furnizor = brand) are documented in `docs/BUSINESS_LOGIC.md`.

---

## Input data files (`docs_input/`, gitignored)

What each Excel file contains and which sheets matter.

### Raw transaction data (source of truth)

**vanzari_01.03.2026.xlsx** — the main sales database. Contains 2024 complete + 2025 complete + 2026 YTD (Jan-Feb).
Key sheet: `Baza` — row-level transactions with columns:
`Luna, An, datadl, nrdl, cantit, pvanz, tva, pcump, Val_B, Val_Net, Val_Achiz, Value_USD, Marja_B, Client, factout, numeag, procent, adr_livr, [SKU name]`
Other sheets are pivot tables built on Baza: Agent Gama Client Marja, Agent Gama An, Gama_Ani, Basilur luna an, top SKU, Online, Selgros pivots.

**raport Dragos 31_03_2026.xlsx** — sales analysis through March 2026. Same Baza structure + pivot sheets broken down by agent (Bogdan, Oana, Claudiu separately). Useful for Q1 2026 margin analysis.

**vanzari 2025.xlsx** — full year 2025, likely similar Baza structure. Not yet inspected in detail.

### Reporting & planning templates (originally empty — the data-pipeline gap)

**TORB_Dashboard_Managerial_FMCG.xlsx** — 8 sheets: DASHBOARD, README, CONTROL, INPUT_SALES, INPUT_PNL, INPUT_AR_AP, INPUT_INVENTORY, Input_PnL_Managerial.
Tracks: Net Sales, Gross Profit, Margin%, OPEX, EBITDA, Cash, DSO, Stock Days, DPO, CCC — by 6 brands (Basilur, Celmar, Delaviuda, Leonex, Solvex, Toras).
Template was empty; superseded by the webapp dashboard.

**TORB_FMCG_FULL_AUTOMATED_DASHBOARD.xlsx / TORB_Dashboard_RO_RON_Calibrat_UPDATED.xlsx / FMCG_Executive_Dashboard_Advanced_Pharma_v2.xlsx** — additional dashboard variants. Not yet inspected in detail.

### Bonus & team structure

**bonusare_torb_structura_echipa.xlsx** — 7 sheets: 00_Instructiuni, 01_Echipa, 02_Rol_KPI, 03_Targeturi_2026, 04_Actuale_2026, 05_Calcul_Bonus, 06_Centralizare.
- 01_Echipa: 5 employee IDs (MGR_PHTT_01, KAM_IKA_01, KAM_MIX_01, AG_TT_01, AG_TT_02)
- 02_Rol_KPI: KPI weights per role (Net Sales, Margin, Active Clients, Collections, Forecast, Promo Exec)
- 05_Calcul_Bonus: full bonus formula with payout curve and penalty logic (49 columns wide)
- 06_Centralizare: monthly bonus tracker — was empty; superseded by the webapp bonus module

**simulator_bonus_1_om_avansat.xlsx / Target_bonusare/** — advanced bonus simulator and per-rep targets. Not yet inspected.

### Individual rep sales plans

**Cantitativ_Claudiu2026.xlsx / Cantitativ_Oana2026.xlsx / Cantitativ_Bogdan2026.xlsx** — per-rep quantitative targets for 2026. Not yet inspected.

**model_livrabil_plan_vanzari_RON.xlsx** — sales plan template for each rep. Sheets: Liste, Instructiuni, Repere vanzari, Summary, Situatie actuala, Oportunitati, Target propus, Organizare flow.
- `Repere vanzari`: pre-populated with aggregated benchmarks from vanzari_01.03.2026.xlsx (top clients, top brands, monthly phasing)
- `Summary`: individual rep fills in name, role, clients, targets, top opportunities, blockers
- `Situatie actuala` / `Oportunitati` / `Target propus`: 200-300 row detail sheets (likely one row per client)

### Financial

**Bal Dec.pdf** — December balance sheet. Not yet read.

### Receivables (solduri neîncasate)

**neinc DD MM.xls** (e.g. `neinc 30 06.xls`) — consolidated ERP receivables export, one row
per open document (invoice/advance). Uploaded on `/solduri-neincasate` (saved to
`docs_input/rapoarte/`, `tip='solduri'` on the shared `/api/upload/<tip>` pipeline), parsed by
`etl/import_solduri_neincasate.py`. Key columns: `datadl` (doc date), `term_pl_cl` (payment
term in days), `sumdeincas` (outstanding, signed), `numecli`/`codcli`, `numeag` (agent/channel),
`factout` (invoice), `plafon` (credit ceiling), `nume` (channel → stored as `canal`). The file's
`scadenta` column is the term in days, **not** a date — the due date is computed downstream.

---

## Deploy pipeline (`.github/workflows/deploy_VPS.yml`)

Jobs (as of 2026-06-11):
`lint` (ruff) → `test` (pytest) → `security` (pip-audit, **blocking**) → `deploy_dev` → `test_dev` (smoke on https://app.robrands.ro:5001) → `approve_prd` (GitHub Environment `production`, manual gate) → `deploy_prd` → `test_prd` (smoke on https://app.robrands.ro).

- Deploys via `appleboy/ssh-action`, SSH port 2112. Prod path `/var/www/html/torb-py` (service `torb-py`), dev path `/var/www/html/torb-py-dev` (service `torb-dev`). See §Infrastructure below for the full VPS layout.
- `gunicorn` is installed from `requirements.txt` (linux-only environment marker); local Windows dev uses `waitress`.
- Migrations run explicitly (`python migrations/runner.py data/torb.db`) before service restart — a failed migration aborts the deploy and leaves the running service untouched.
- Prod deploy saves the previous SHA to `.previous_deploy_sha` — used by the manual **Rollback Production** workflow (Actions tab, type `ROLLBACK` to confirm).

### Secret injection pattern

Secrets are passed via `env:` + `envs:` into the SSH session, then written to `.env` with grep-v/append:
```bash
grep -v '^VAR=' .env > .env.tmp && mv .env.tmp .env
echo "VAR=${VAR}" >> .env
```

GitHub Actions secrets: `FLASK_SECRET_KEY`, `ANTHROPIC_API_KEY`, `EMAG_USERNAME`, `EMAG_PASSWORD`, `EMAG_WAREHOUSE_ID`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `SMTP_USER`, `SMTP_PASSWORD`, `VPS_HOST`, `VPS_USERNAME`, `VPS_SSH_KEY`.

Non-secrets hardcoded in the deploy script: `SHOPIFY_SHOP_DOMAIN=basilur-tea-romania.myshopify.com`, `SHOPIFY_LOCATION_ID=110603567429`, `SHOPIFY_STOCK_SAFETY_THRESHOLD=5`, `EMAG_STOCK_SAFETY_THRESHOLD=5`.

### `.env.example` convention

- `[SECRET]` marker on lines that must come from GitHub secrets (left empty in the file)
- Non-sensitive vars carry real production values directly

---

## Infrastructure — VPS server

> **Maintenance rule:** this section is the single source of truth for **current** server facts.
> Whenever a server question is answered (ownership, permissions, users, services, ports, cron
> entries), record the answer here immediately — future sessions must be able to answer these
> questions from this file without asking.
>
> **Dated changes, resolved security items, and applied checklists live in
> `docs/TECHNICAL_history.md`** — move narrative there once an item is done; keep this section
> lean (current state only). Pending infrastructure work is tracked in `docs/BACKLOG.md`.
>
> ⛔ **Do not open `TECHNICAL_history.md` automatically.** It is a write-mostly archive — read it
> **only** when explicitly investigating a past change.

### Server

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

**Full reproduction manual:** `docs/manuals/server/manual_server.typ` (compiled PDF:
`docs/manuals/manual_server.pdf`) — verbatim systemd units, nginx vhosts, a from-scratch rebuild
runbook, and the secrets inventory. Keep this section and the manual in sync.

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

### Environments

**Production**

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

**Dev / Test**

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
| Deploy trigger | Push to `main` via `deploy_dev` CI job |

### Nginx

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

### Systemd services

```bash
sudo systemctl status torb-py      # production
sudo systemctl status torb-dev     # dev/test
sudo systemctl restart torb-py
sudo systemctl restart torb-dev
```

Service files:
- `/etc/systemd/system/torb-py.service`
- `/etc/systemd/system/torb-dev.service`

### Firewall (ufw)

Active, default deny incoming. Current rules (IPv4+IPv6):

| Port | Protocol | Purpose |
|---|---|---|
| 2112 | TCP | SSH (only port sshd listens on) |
| 80 | TCP | HTTP (redirects to HTTPS) |
| 443 | TCP | HTTPS — production |
| 5001 | TCP | HTTPS — dev/test |

SSH is key-only (`PasswordAuthentication no`); `PermitRootLogin prohibit-password`; fail2ban
`[sshd]` jail active. Recovery if the key is lost: cyberfolks console (local console, not SSH).

### Repository

GitHub: `https://github.com/ifrimdrag-hue/TorbApp`

Git safe directories configured on server:
```bash
git config --global --add safe.directory /var/www/html/torb-py
git config --global --add safe.directory /var/www/html/torb-py-dev
```

### Database backups (production only)

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

### Email / SMTP (password-reset)

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

### OpenClaw gateway (agent integration)

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

> Setup history, fixes, and the security lockdown narrative are in `docs/TECHNICAL_history.md`
> (load-on-demand archive — only open it if investigating a past change).

### Application logging

`app/logging_config.py` (`setup_logging()`, idempotent) centralises logging; `create_app()`
routes through it. Two rotating file handlers on the root logger:
- **`logs/app.log`** — all levels per `LOG_LEVEL` (default INFO), 2 MB × 5 backups.
- **`logs/errors.log`** — ERROR-only, 1 MB × 3 backups, for fast triage.

Noisy third-party loggers (`werkzeug`, `httpx`, `urllib3`) are raised to WARNING so `app.log`
isn't flooded with per-request `200 -` access lines; genuine 4xx/5xx still surface. Console
echo only when `FLASK_DEBUG` is set.

### Useful one-liners

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

Pending infrastructure work (reboot, swap, CSP follow-up, etc.) is tracked in `docs/BACKLOG.md` §Infrastructure.

---

## Romanian strings in `.py` files — encoding rules

**Never use the Edit tool to write Romanian string literals into `.py` files.** It can silently convert straight ASCII quotes `"` to curly quotes (U+201C/U+201D), which are invalid Python string delimiters and fail ruff with `invalid-syntax`. The project's Python files also have a history of double-encoded UTF-8 (mojibake).

**For new Romanian strings:** write them via a targeted Python replacement script run through Bash:
```bash
python -c "
with open('app/blueprints/auth.py', 'r', encoding='utf-8-sig') as f:
    content = f.read()
content = content.replace('old_ascii_only_placeholder', 'Textul corect în română.')
with open('app/blueprints/auth.py', 'w', encoding='utf-8-sig') as f:
    f.write(content)
"
```

**Detection** (Read-tool display on Windows CP1252 terminals shows correct UTF-8 as mojibake — always check raw bytes, never trust the display):
```python
with open('file.py', 'rb') as f:
    data = f.read()
print('ă wrong' if b'\xc3\x84\xc6\x92' in data else 'ă ok')
print('ț wrong' if b'\xc3\x88\xe2\x80\xba' in data else 'ț ok')
```

**Fix script for double-encoded Romanian chars:**
```python
with open('file.py', 'rb') as f:
    data = f.read()

replacements = [
    (b'\xc3\x84\xc6\x92', b'\xc4\x83'),          # ă
    (b'\xc3\x88\xe2\x80\xba', b'\xc8\x9b'),      # ț
    (b'\xc3\x88\xc5\xa1', b'\xc8\x9a'),          # Ț
    (b'\xc3\x88\xe2\x84\xa2', b'\xc8\x99'),      # ș
    (b'\xc3\x83\xc2\xae', b'\xc3\xae'),          # î
    (b'\xc3\x83\xc5\xbd', b'\xc3\x8e'),          # Î
    (b'\xc3\x83\xc2\xa2', b'\xc3\xa2'),          # â
    (b'\xc3\x84\xe2\x80\x9a', b'\xc4\x82'),      # Ă
]
for wrong, correct in replacements:
    data = data.replace(wrong, correct)

with open('file.py', 'wb') as f:
    f.write(data)
```

**Em-dash corruption:** `—` (U+2014) sometimes appears double-encoded; fix with `data.replace(b'\xc3\xa2\xe2\x82\xac\x22', b'\xe2\x80\x94')`. Curly quotes that snuck into delimiters: `content.replace('“', '"').replace('”', '"')`.

---

## Frontend conventions

**Error display — always use the shared `AppError` modal.** `app/static/js/app-error.js`
is loaded on every page via `base.html`. Any error handler that surfaces a message to
the user must route it through it, so error UX stays consistent app-wide and long
messages are fully visible (scrollable + copy button) instead of truncated inline text:

```js
AppError.show(subtitle, message, title);   // title defaults to "Eroare"
// e.g. AppError.show(file.name, d.mesaj, 'Eroare la import');
```

The modal markup is injected lazily on first call — pages need no per-page HTML. Do not
add ad-hoc per-page error modals or inline red-text error strings for anything a user
may need to read in full. Reference implementation: the upload zones in `actualizare.html`.

---

## Typst user manuals (`docs/manuals/`)

**Accuracy — verify every claim against source before writing.** The login manual shipped with four inaccuracies (wrong nav paths, a non-existent label, a false form-field claim). Before writing a section, read:
- the route handlers in `app/blueprints/` — exact error messages, redirects, validation, thresholds (copy constants like `_RATE_LIMIT` / `timedelta` values, never paraphrase)
- the Jinja templates — exact button/link labels, form field names, `{% if %}` conditional UI
- `app/templates/base.html` — sidebar sections, dropdowns, footer links

**Compiling — set `--root` to the repo.** Manuals reference the shared logo via `../img_shared/logo.png`, which sits above the per-manual folder; Typst refuses paths outside the project root, so compile with:
```
typst compile --root . docs/manuals/<name>/manual_<name>.typ docs/manuals/manual_<name>.pdf
```
**Output PDFs go flat into `docs/manuals/` (not into the per-manual source folder).** Only the compiled `docs/manuals/*.pdf` files are git-tracked; the per-manual subfolders (`.typ` sources + `img/`) are not versioned.

**Placeholder images — generate at creation time.** Every `image("img/x.png")` reference needs a gray placeholder PNG when the `.typ` file is written, otherwise Typst fails to compile and the IDE preview shows nothing. Size to the expected aspect ratio, label with the filename. PowerShell pattern:
```powershell
Add-Type -AssemblyName System.Drawing
$dir = "docs\manuals\<manual>\img"
$images = @(@{name="screenshot_name"; w=800; h=500})
foreach ($img in $images) {
    $bmp = New-Object System.Drawing.Bitmap($img.w, $img.h)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::FromArgb(220, 220, 220))
    $font = New-Object System.Drawing.Font("Arial", 18)
    $size = $g.MeasureString($img.name, $font)
    $g.DrawString($img.name, $font, [System.Drawing.Brushes]::Gray, ($img.w - $size.Width)/2, ($img.h - $size.Height)/2)
    $font.Dispose(); $g.Dispose()
    $bmp.Save("$dir\$($img.name).png", [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}
```
