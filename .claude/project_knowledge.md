# Project Knowledge — durable technical notes

Consolidated from AI session memory on 2026-06-11. Update in place when facts change; this file is the single source for the notes below (they are no longer kept in session memory).

---

## Data — SQLite database & Excel

`data/torb.db` — 131,898 transaction rows, 2024-01-03 → 2026-03-31.
Main table: `tranzactii` (31 columns). Useful views: `v_vanzari_an_furnizor`, `v_vanzari_luna_agent`, `v_vanzari_luna_client`, `v_top_sku`, `v_clienti`.
To rebuild: `python etl/import_to_sqlite.py`

Forecast tables live here too — see `app/forecast/README.md`.

**Reading Excel files** — use `openpyxl` with `read_only=True` for large files:
```python
import openpyxl
wb = openpyxl.load_workbook('file.xlsx', data_only=True, read_only=True)
```

---

## Deploy pipeline (`.github/workflows/deploy_VPS.yml`)

Jobs (as of 2026-06-11):
`lint` (ruff) → `test` (pytest) → `security` (pip-audit, **blocking**) → `deploy_dev` → `test_dev` (smoke on https://app.robrands.ro:5001) → `approve_prd` (GitHub Environment `production`, manual gate) → `deploy_prd` → `test_prd` (smoke on https://app.robrands.ro).

- Deploys via `appleboy/ssh-action`, SSH port 2112. Prod path `/var/www/html/torb-py` (service `torb-py`), dev path `/var/www/html/torb-py-dev` (service `torb-dev`). See `context/infrastructure.md` for the full VPS layout.
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

## Shopify stock sync (delivered 2026-06-03)

Mirrors the eMAG pattern: `preview()` → user review → `sync()`.

- `app/automations/stocuri_shopify/api_client.py` — OAuth token cache (24h expiry, auto-refresh, in-memory `_TokenCache` with asyncio.Lock), paginated inventory fetch via `location.inventoryLevels` (50/page), `inventorySetQuantities` mutation (batches of 50)
- `app/automations/stocuri_shopify/orchestrator.py` — `preview()` / `sync()` / `preview_shopify_only()`
- `app/automations/stocuri_shopify/request_logger.py` — rotating JSON log, last 20 entries → `logs/shopify_req.json`, token masked as `***`
- `app/blueprints/stocuri_shopify.py` — `/preview`, `/sync`, `/connection-test`
- Unified page `/stocuri` (served by `stocuri_emag.py`): radio btn-group switches platforms, driven by a `PLATFORMS` config object in `app/static/js/stocuri.js`; old `/stocuri/emag` and `/stocuri/shopify` redirect there

**Auth:** OAuth client credentials. App "SyncStoc" created in the Shopify Dev Dashboard (not legacy admin). Scopes: `write_inventory, read_inventory, read_locations, read_products`. Token endpoint: `POST https://{shop}/admin/oauth/access_token` with `grant_type=client_credentials`. GraphQL API version `2025-04`.

**Gotchas fixed during delivery (do not reintroduce):**
1. The field on `InventoryLevel` is `item`, not `inventoryItem`
2. `inventorySetQuantities` requires `ignoreCompareQuantity: true` (mandatory since API 2025-04)
3. Switching the platform radio must reset the file input `.value`, or re-selecting the same file fires no change event
4. Safety threshold: stock ≤ threshold is sent as 0; independent per platform (`EMAG_STOCK_SAFETY_THRESHOLD`, `SHOPIFY_STOCK_SAFETY_THRESHOLD`), default 5
5. SKU matching uses `_normalize_sku()` from `csv_filler.py`: strips leading apostrophe + trailing `-XX` suffix; matches `codmare` from the internal report to the Shopify variant SKU

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

## Typst user manuals (`docs/manuals/`)

**Accuracy — verify every claim against source before writing.** The login manual shipped with four inaccuracies (wrong nav paths, a non-existent label, a false form-field claim). Before writing a section, read:
- the route handlers in `app/blueprints/` — exact error messages, redirects, validation, thresholds (copy constants like `_RATE_LIMIT` / `timedelta` values, never paraphrase)
- the Jinja templates — exact button/link labels, form field names, `{% if %}` conditional UI
- `app/templates/base.html` — sidebar sections, dropdowns, footer links

**Compiling — set `--root` to the repo.** Manuals reference the shared logo via `../img_shared/logo.png`, which sits above the per-manual folder; Typst refuses paths outside the project root, so compile with:
```
typst compile --root . docs/manuals/<name>/manual_<name>.typ docs/manuals/<name>/manual_<name>.pdf
```
Only the compiled `*.pdf` is git-tracked (`.gitignore` ignores `docs/manuals/**` except dirs + PDFs); `.typ` sources are not versioned.

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

---

## Virtual brands (KingsLeaf, Tipson, Organsia)

`KingsLeaf`, `Tipson`, and `Organsia` are **virtual sub-brands of Basilur** — they
are not distinct ERP suppliers. All three ship from Basilur (Sri Lanka) on the same
PFI/shipment and are split out at import time from the product-name prefix:

| Brand     | SKU-name prefix    | Notes |
|-----------|--------------------|-------|
| KingsLeaf | `KL ` (KL + space) | ERP product code range 90xxx |
| Tipson    | `TS ` (TS + space) | ERP product code range 80xxx |
| Organsia  | `B.ECO ORGANSIA`   | Subset of the `B.` Basilur prefix — MUST be checked BEFORE the generic `B.` rule |

**Two different naming conventions — the trap for adding another virtual brand:**
Organsia (and only Organsia, since it shares Basilur's `B.` ERP prefix) has product
names that differ across tables depending on data source:
- `stoc.sku` and `tranzactii.sku` come from ERP exports and hold names like
  `B.ECO ORGANSIA APPLE CINNAMON...` → match prefix **`B.ECO ORGANSIA`**.
- `produse.descriere` comes from the pricing/monitorizare spreadsheet (`Oferta
  produse TORB LOGISTIC CU ORGANSIA...xlsx`) and holds names like
  `ORGANSIA - ORGANIC - BOX - ...` → match prefix **`ORGANSIA`** (the `B.ECO
  ORGANSIA` form never appears in `produse`).

KingsLeaf's `KL ` and Tipson's `TS ` prefixes do not have this split — they look
the same in every table, because they don't overlap with a shared ERP letter
prefix the way Organsia/Basilur (`B.`) do.

**Where the rule lives (duplicated by design — no shared module):**
- `etl/import_stoc.py` — `derive_furnizor()` matches `sku.upper().startswith("B.ECO ORGANSIA")` (checked before the generic `s.startswith("B.")` Basilur rule), `s.startswith("KL ")`, `s.startswith("TS ")`; `derive_gama()` maps `furnizor` → `gama` via `gama_map`
- `etl/import_vanzari_erp.py` — `_furnizor_from_prefix()`
- `etl/import_vanzari_tobra_auchan.py` — `derive_furnizor()`
- `etl/import_preturi.py` — `import_monitorizare()` overrides `furnizor`/`brand` to `"Organsia"` for the `produse` table when `descriere.upper()` starts with `"ORGANSIA"` (the pricing spreadsheet uses this form, not the ERP `B.ECO ORGANSIA` form — the `"B.ECO ORGANSIA"` check in that same `if` is defensive and doesn't currently match any `produse` row)
- `etl/update_data.py` + `etl/rebuild_db.py` — `GAMA_MAP` / lead-time seed

**Migrations backfill by table, using the prefix that matches each table's naming
convention.** Migration `0012` (`migrations/0012_20260701_organsia_brand.py`) is
the reference example:
- `stoc` / `tranzactii`: `UPDATE ... WHERE furnizor='Basilur' AND sku LIKE 'B.ECO ORGANSIA%'`
- `produse`: `UPDATE ... WHERE furnizor='Basilur' AND descriere LIKE 'ORGANSIA%'`

**Rolled into "Basilur family" reports:** the four brands are grouped via
`BASILUR_BRANDS` / `_BASILUR_IN` in `app/queries/forecast.py`, `BASILUR_BRANDS`
in `app/blueprints/reports.py`, and `BRANDS` in `app/exports/ppt_export.py`.
The Basilur report template is `app/templates/raportare_basilur.html`.

**Lead time:** all four share Basilur's 120-day (4-month) extra-EU lead time and
Christmas seasonality — seeded in `termene_aprovizionare`.

**Adding another virtual brand:** first check whether it shares an ERP letter
prefix with an existing family (like Organsia shares `B.` with Basilur) — if so,
expect the same `stoc`/`tranzactii` (ERP-name prefix) vs `produse`
(spreadsheet-name prefix) split, and identify both prefixes before writing any
code. Then: add the prefix rule to the three ETL derivation functions (before the
generic `B.` check if it's a `B.` subset), add to `GAMA_MAP` and the
`rebuild_db.py` seed, write a migration to seed `termene_aprovizionare` and
backfill existing `stoc`/`tranzactii`/`produse` rows (each with its own matching
prefix), then extend the `BASILUR_BRANDS` constants + template colors. See
migration `0012` for the Organsia example.

---

## Tech-debt & infrastructure backlog

Combines the leftovers of the 2026-05-28 code audit (re-verified against code on 2026-06-11) and the infrastructure gaps found in the 2026-06-11 stack assessment. Resolved since the audit:
- ~~`queries.py` connection leaks~~ — the `app/queries/` package now goes through `db.query()`/`get_db()`, which close transient connections in `finally` (request-scoped ones close on teardown)
- ~~`SHOPIFY_SHOP` vs `SHOPIFY_SHOP_DOMAIN` mismatch~~ — `config.py` uses only `shopify_shop_domain`
- ~~`scripts/` vs `tools/` directory-rule inconsistency~~ — `scripts/` no longer exists and CLAUDE.md no longer references it (a stale `scripts/` line remains in `.gitignore`; see the last backlog item)

Resolved 2026-06-11 (backup engine delivery):
- ~~No backup strategy for `data/torb.db`~~ — `app/backup_db.py` + `etl/backup_db.py` CLI: daily cron on prod, pre-deploy backup in CI, admin UI at `/admin/db` with guarded restore. 15-day retention, min 3 kept. See `context/infrastructure.md`.
- ~~`PRAGMA busy_timeout` missing~~ — added to `_PER_CONN_PRAGMAS` in `app/db.py` (5s).

Remaining, in priority order:
1. **JSON file storage has no cross-process safety** (`app/automations/*/storage.py`, `_shared/snapshot.py`, `_shared/prices.py` — plain `write_text`, no locking). The original "single-user risk accepted" rationale no longer holds: the app is multi-user with auth and prod runs 3 gunicorn workers, so even `threading.Lock` wouldn't suffice. Concurrent writes can lose updates or truncate files. Fix: move this state into SQLite (migrations + helpers already exist) or use OS-level file locking.
2. **No disaster-recovery runbook for the VPS** — prod, dev, nginx, and the DB share one machine at one provider. Mitigated: the hosting provider backs up the VPS itself and the DB now has its own backups. Document a "rebuild from scratch" runbook in `context/infrastructure.md` (packages, systemd units, nginx blocks, certbot, firewall).
3. **Data ingestion is manual Excel exports** (`docs_input/`, upload-based stock sync) — the real scaling bottleneck, hit long before Flask or SQLite limits. The SmartBill/ERP → pipeline API integration (strategic plan, Pilon 5.1) should be prioritized above the Postgres migration.
4. **No background-job mechanism** — forecasts run via PowerShell CLI, syncs are request-driven, but Pilon 5's roadmap (weekly AI sales briefs, automated bonus emails, churn flags) is all scheduled work. No Celery needed: cron on the VPS calling CLI scripts covers 2026–2027 — just design upcoming features as CLI-invocable jobs, not Flask routes.
5. **Shared `call_claude()` helper** — 6 separate Anthropic call sites (`app/ai.py`, `forecast_agent.py`, `claude_client.py`, `post_generator.py`, `campaign_generator.py`, `ai_suggestions.py`); error handling and model config drift between them.
6. **SQLite → Postgres migration** — trigger on symptoms ("database is locked" errors), not on the revenue milestone; with WAL + busy_timeout this likely stays dormant for a long time. The strategic plan anticipates it at ~30M RON revenue.
7. **`Start-Hub.ps1` launches the Flask dev server** (`python app\app.py`) instead of `waitress`, which is in requirements for this purpose. Dev-only launcher, low risk, quick fix.
8. **Merge `postari/instagram.html` + `postari/facebook.html`** (was listed under `campanii/`; templates moved). Needs UI testing.
9. **eMAG/stock CSS still lives in the global `style.css`** — separate when next touching those styles.
10. **Accessibility pass** — only 6 `aria-label`s across all templates.
11. **Remove the stale `scripts/` line from `.gitignore`** — if anyone recreates that directory, its files would silently never be committed.
12. **Off-VPS copy of DB backups** (low priority by decision 2026-06-11: the hosting provider backs up the whole VPS). If ever needed: pull `data/backups/` to a local machine via scheduled `scp` — admins can also download backups manually from `/admin/db`.
