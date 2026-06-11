# Project Knowledge — durable technical notes

Consolidated from AI session memory on 2026-06-11. Update in place when facts change; this file is the single source for the notes below (they are no longer kept in session memory).

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

GitHub Actions secrets: `FLASK_SECRET_KEY`, `ANTHROPIC_API_KEY`, `EMAG_USERNAME`, `EMAG_PASSWORD`, `EMAG_WAREHOUSE_ID`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `VPS_HOST`, `VPS_USERNAME`, `VPS_SSH_KEY`.

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

## Tech-debt backlog — deliberately skipped in the 2026-05-28 audit

Known and accepted at the time; revisit when relevant:
- `queries.py` connection-leak fixes (complex try/finally, risk to data integrity)
- Extracting a shared `call_claude()` helper across the 5+ AI modules
- Thread locking for JSON file storage (single-user risk accepted)
- Merging `instagram.html` + `facebook.html` (needs UI testing)
- Aria-labels / accessibility pass
- eMAG CSS separation from the global stylesheet
- `SHOPIFY_SHOP` vs `SHOPIFY_SHOP_DOMAIN` naming mismatch in `config.py` (documented in `.env.example`, not fixed)
- `Start-Hub.ps1` launches `python app\app.py` instead of `waitress`
- `scripts/` is gitignored but `tools/` is not — directory-rule inconsistency
