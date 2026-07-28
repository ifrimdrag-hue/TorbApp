# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Stock sync: Shopify EAN-fallback matching (2026-07-10)

The ERP renumbered several `codmare` values, which silently broke the Shopify stock sync's only match key (`codmare` ↔ Shopify variant SKU) — affected products kept a frozen stock on Shopify (oversell risk). eMAG was unaffected (it matches on `codbare`/EAN). Renumbered pairs confirmed by name during verification: Shopify SKU `70177-00` vs ERP `70173-00` (Earl Grey 25), `70184-00` vs `70290-00` (English Breakfast 25), `70771-00` vs `70293-00` (English Afternoon 100g), `70427-00` vs `70419-00` (Moroccan Mint 100g).

- **EAN fallback in the Shopify preview matcher** (`app/automations/stocuri_shopify/orchestrator.py`) — items match by normalized `codmare` first, then by report `codbare` vs the Shopify variant `barcode`, so the sync survives ERP code renumbering. `ShopifyPreviewRow` gains `matched_by` (`sku`/`ean`); codmare covered via an EAN match no longer appear in `skus_not_in_shopify`; the "no codmare" warning now fires only for rows with neither codmare nor EAN. An item without SKU can now still sync via barcode.
- **GraphQL inventory fetch includes `variant.barcode`** (`app/automations/stocuri_shopify/api_client.py`).
- **UI**: the `/stocuri` Shopify summary shows a "Match pe EAN" counter (`summary.matched_by_ean`; `app/static/js/stocuri.js`).
- **Verification vs live exports (2026-07-10)** — full comparison of the ERP warehouse report against the eMAG offer export and the Shopify inventory CSV: drift analysis and per-platform catalog issues (products with stock absent from the ERP report, duplicate EANs/SKUs) in `docs/analysis/2026-07-10-stock-sync-verification.md`; owner data-cleanup actions tracked as BACKLOG item 14.
- Files: `app/automations/stocuri_shopify/orchestrator.py`, `app/automations/stocuri_shopify/api_client.py`, `app/static/js/stocuri.js`, `tests/test_shopify_orchestrator.py` (new). Tests: 343 passing (+7).

### P&L redesign F0: correctness foundation (2026-07-08)

Phase F0 of `docs/plans/2026-07-08-pnl-redesign.md` — the P&L is now structurally correct with any subset of months imported, and every import is validated and visible.

- **Full-replace import** — re-importing a corrected balance now DELETEs all rows of that (entitate, an, luna) and inserts the new file in one transaction, so accounts that disappeared from the corrected file no longer survive as ghosts. Migration **0040** rebuilds `pnl_balante_raw` without `ON CONFLICT REPLACE` (plain UNIQUE kept) and adds `replaced`/`validari` columns to `pnl_import_log`. The import log records how many rows were replaced.
- **Monthly values from the month's own turnovers** — `compute_pnl_month` now reads `rulld` (expense accounts) / `rullc` (revenue accounts, chosen by mapping semn) instead of Δ`rulcd`, so a month renders correctly even when the prior month is missing (the C2 "cumulative shown as monthly" bug is gone). YTD comes from cumulative `rulcd` at the through-month — the figure that reconciles with account 121. When the prior month exists, a Δ`rulcd` cross-check flags per-line divergences as ⚠ tooltips in the grid (caught a real 499.36 RON prior-period correction on account 628, Torb Mar 2026).
- **Import validations** persisted as JSON per import and surfaced in the upload-zone summary and `/pnl/import` history: `echilibru` (Σdebit=Σcredit on opening/closing/turnover), `inlantuire` (cumulative-turnover chaining vs the prior month — `sid/sic` proved to be *year*-opening balances in these files, so chaining is checked on `rulcd/rulcc` increments instead), `reconciliere_121` (computed net profit YTD vs the 121 balance in the same file). Imports always succeed; problems are warnings.
- **Freshness header on /pnl** — per entity: last imported month, import timestamp, and a 121-reconciliation badge (verde "reconciliat" / roșu "diferență X RON" / gri "verificare parțială"). Missing months inside the displayed range render as em-dash columns with a "balanță neîncărcată" tooltip, never as zero.
- **Real-data validation** — all 18 balance files re-imported through the new path: net profit YTD reconciles with 121 to ±0.01 for Tobra 2025 (−536,776.35), Tobra 2026 Q1 (+26,414.76), Torb 2026 Q1 (+355,255.31); Torb 2026 monthly CA unchanged vs the old method (Jan 1,134,530 / Feb 1,448,865 / Mar 1,388,083); double-import leaves identical row counts. Torb Jan/Feb 2026 show a real 0.52 RON 121 gap (clears by March) — correctly flagged as a warning.
- Files: `migrations/0040_20260708_pnl_full_replace.py` (new), `app/pnl_import.py`, `app/pnl_logic.py`, `app/queries/pnl.py`, `app/queries/__init__.py`, `app/blueprints/pnl.py`, `app/templates/pnl/pnl.html`, `app/templates/pnl/import.html`, `app/templates/actualizare.html`, `tests/test_pnl_import.py`, `tests/test_pnl_logic.py`. Tests: 336 passing (+12).

### Actualizare: multi-file upload for P&L balances (2026-07-08)

The **Balanțe P&L** drop zone now accepts multiple .xls files at once (drag a whole selection or multi-pick from the file dialog). Files import sequentially with per-file progress ("3/18: bal 03 2026 tobra.xls"), ending with a total (files + rows) or an error summary listing exactly which files failed. Other zones stay single-file by design (replace-style imports) but now show an explicit error when handed multiple files instead of silently importing only the first. File: `app/templates/actualizare.html`.

### P&L: account-mapping screen + toolbar links (2026-07-08)

New read-only screen **/pnl/mapare** showing the full account → P&L-line mapping (grouped by P&L line, +/− sign badge, category) plus a warning panel listing any class-6/7 accounts found in imported balances that are **not** mapped (their amounts would silently miss the P&L — exactly the 7583 bug class). Green all-clear when coverage is complete. The /pnl toolbar gains links to Mapare conturi, Import balanțe and Alarme (previously unreachable by click). Files: `app/queries/pnl.py` (+`pnl_mapping_rows`, `pnl_unmapped_accounts`), `app/queries/__init__.py`, `app/blueprints/pnl.py`, `app/templates/pnl/mapping.html` (new), `app/templates/pnl/pnl.html`.

### P&L: first real-data validation + asset-disposal mapping fix (2026-07-08)

Imported the owner's real balance files (16 .xls — Tobra full 2025 + Jan–Mar 2026, Torb Mar 2026) through `pnl_import` and reconciled the computed P&L against the account-121 balance for every period: **all match to the cent** after one fix.

- **Fix** — migration **0039** maps `7583` (VENITURI DIN CEDARI DE ACTIVE → Alte venituri exploatare, +1) and its pair `6583` (→ Alte cheltuieli exploatare, −1), both absent from the 0033 seed. Tobra 2025 net profit had missed the 121 balance by exactly 7583's 16,426.43 RON.
- **Validated** — Tobra 2025 (−536,776), Tobra 2026 Q1 (+26,415), Torb 2026 (+355,255) all reconcile to ±0.01 vs balance; `/pnl` grid renders for entity and group views.
- **Known data gap** — Torb has only the March 2026 balance, so its "March" column (and the group view) actually holds cumulative Q1; Jan/Feb 2026 Torb files are needed for true monthly splits. 2025 Torb balances needed for the year-over-year comparison.
- Files: `migrations/0039_20260708_pnl_map_cedari_active.py`, `tests/test_pnl_import.py` (+1), `tests/test_pnl_db.py` (seed count 33 → 35). Tests: 324 passing.

### Actualizare: Solduri drag-and-drop zone (2026-07-08)

Added a **Solduri neîncasate** drop zone to the Actualizare Date page so the receivables report is uploaded alongside the other ERP files (backend `tip='solduri'` → `import_solduri_neincasate.py` already existed; only the zone + history icon/label were missing). Also widened the row-count parser regex to accept `randuri` (plain-a) so the solduri import shows its count instead of `?`. Files: `app/templates/actualizare.html`, `app/blueprints/actualizare.py`. Verified end-to-end on the real `neincasate.xls` (1,716 rows).

### Actualizare: P&L balance upload as a drag-and-drop zone (2026-07-08)

The P&L balance (.xls) upload now lives on the **Actualizare Date** page next to the other ERP drop zones, so all file updates are in one place. Added a "Financiar (P&L)" section with a **Balanțe P&L** drop zone; it posts to the existing synchronous `/pnl/api/upload` endpoint (no backend change) and shows the imported-row count inline. The standalone `/pnl/import` page (folder scan + upload) is left intact. Stock (`Stoc ERP`) was already a drop zone on this page. File: `app/templates/actualizare.html`.

### Admin RBAC: dynamic roles + nav authorization matrix (2026-07-07)

### Added
- Admin RBAC: dynamic roles (`adm_roles`) + role→nav authorization matrix
  (Admin → Autorizări). Sidebar links and their routes are now gated per role
  (deny-by-default; `admin` is a superuser). Admin module reorganized into three
  tabs (Utilizatori, Mentenanță DB, Autorizări).

### Changed
- Renamed `users` table to `adm_users`; new admin tables use the `adm_` prefix
  (`adm_roles`, `adm_role_nav`). Two migrations: **0037** creates `adm_roles`/
  `adm_role_nav`, renames `users` → `adm_users`, and seeds `manager`/`viewer`
  with every nav key; **0038** rebuilds `adm_users` to drop the legacy
  `CHECK(role IN ('admin','manager','viewer'))` so dynamic role names are
  allowed.
- Sidebar is now rendered from a canonical `app/nav_registry.py` (single source
  of truth for links, the matrix, and 403 enforcement via `app/authz.py`).

### Produse: de-duplicate EAN-as-SKU twins (Solvex/Toras) (2026-07-07)

The tranzactii backfill in `import_preturi.py` created a second produse row per product for suppliers whose transactions use the long concatenated SKU (Solvex, Toras): a bare-EAN SKU row (real name, `ean` NULL) alongside the real master row (numeric code, `ean` + `buc_cutie` + landing costs, placeholder descriere `Articol cod NNN`). 29 twin rows (25 Solvex + 4 Toras).

- **Root cause** — `find_match()` only matched a transaction's 13-digit EAN against catalogued **SKUs**, never the `ean` column, so an already-catalogued product looked new and got a duplicate row.
- **Importer fix** — `find_match()` now also matches by catalogued `ean` → the product is recognised and skipped, so no new twins.
- **Migration 0036** — folds each existing twin into its master: copies the real name onto the master (if still a placeholder), moves selling prices to the master SKU (skip-on-conflict so the master's list price wins over the twin's historical-average price), deletes the twin. Verified on the real dataset: produse 1324 → 1295, no product or price lost, no orphan prices; `resolve_catalog_sku` still maps sales to the master via `ean`.
- Files: `etl/import_preturi.py`, `migrations/0036_20260707_produse_dedup_ean_twins.py`, `tests/test_produse_dedup.py` (2 new). Tests: 289 passing.

### Solduri: cheque value + due-date columns in the invoice list (2026-07-07)

The per-client invoice list (agent → client → facturi) and the main invoice view now show the **cheque amount** and **cheque due date** allocated to each invoice, populated from the report.

- **Data model** — migration **0035** adds `cec_val` (REAL) to `solduri_neincasate`. Replace-only table, no backfill.
- **ETL** — `_merge_cec()` now accumulates `cec_val` = sum of every cheque covering an invoice (an invoice may have several), keeps the **earliest** `scad_cec`, and still drops the folded cheque rows. Previously only the `cec` flag + last date survived; the cheque amount was lost.
- **UI** — `solduri_client.html` gains **Valoare CEC** + **Data CEC** columns; `solduri_neincasate.html` invoice view gains **Val. CEC** next to the existing CEC flag / Scad. CEC. Value shows only where a cheque is allocated, else `—`.
- Files: `etl/import_solduri_neincasate.py`, `migrations/0035_20260707_solduri_cec_val.py`, `app/queries/solduri.py`, `app/templates/solduri_client.html`, `app/templates/solduri_neincasate.html`, `tests/test_solduri.py` (1 new: `test_merge_cec_multiple`). Tests: 287 passing.

### Solduri: fold cheque rows into the invoice they cover (2026-07-07)

The richer ERP export emits a **separate row per cheque** (`cec=1`) that duplicates the balance of the invoice it covers, inflating Total în piață. On the real 1,763-row file this phantom balance was **+60,742.40 RON** across 47 cheque rows.

- **ETL merge** — `import_solduri_neincasate.py` gains `_merge_cec()`, run between parse and insert. A cheque row's `cec_doc` (ERP `_dl`) holds the `nrdl` of the invoice it covers; the four cheque columns (`discount, cec, scad_cec, cec_doc`) are copied onto every matching invoice row and the cheque row is **dropped** so its balance stops double-counting. Cheque rows matching no invoice (historical `original`+`Storno-` pairs netting to 0) are kept as-is.
- **Effect** — one upload, two-pass in code (no manual Excel split); replace-only flow and `/api/upload/solduri` unchanged. Sample: 1763 → 1716 rows, Total în piață −60,742.40, 65 invoice lines flip to `cec=1` with a cheque due date (a single cheque can cover several invoices).
- Owner decisions (2026-07-07): merge in code on the single upload; drop matched cheque rows; keep unmatched ones. Design: `docs/specs/2026-07-07-solduri-cec-merge-design.md`.
- Files: `etl/import_solduri_neincasate.py`, `tests/test_solduri.py` (1 new: `test_merge_cec`). Tests: 12 passing; verified against the real file (−47 rows, −60,742.40). Documented in `docs/BUSINESS_LOGIC.md` §9, `docs/TECHNICAL.md` §Receivables.

### Solduri: per-column table filtering, drop redundant toolbar controls (2026-07-07)

Replaced the two ad-hoc server-side filters (agent dropdown + client search box) on `/solduri-neincasate` with the shared client-side per-column filter widget (`app/static/js/table-filter.js`) across all three views.

- **Grouping buttons kept** (Client/Agent/Factură). The table opts in via `data-filterable` + per-column `data-filter="text|select|number"`; a "Filtre coloane" toggle reveals the filter row and a live count badge shows visible rows. Money/badge cells carry `data-v="<raw>"` so number/select matching parses the raw value, not the RON-formatted text.
- **Filters per view** — invoice: Factură/Client (text), Agent/CEC/Categorie (select), Sumă/Zile (number range); agent: Agent (text), Clienți/Total (number); client: Client (text), Agent (select), Total/Plafon/Zile restanță (number).
- **Removed** the agent `<select>`, client search `<input name=q>` and its submit button (now covered by the column filters); the `agents=` query is dropped from the route. Bucket-card filtering + agent drill-down links stay server-side (a dismissible "Agent: X" chip clears a drilled-down agent).
- Files: `app/templates/solduri_neincasate.html`, `app/blueprints/solduri.py`. Widget usage documented in `docs/TECHNICAL.md` §Frontend conventions. Tests: 11 solduri tests pass (route smoke covers all three views); verified attributes render + old controls gone.

### Solduri: support richer ERP export + capture cheque/discount fields (2026-07-07)

The newer "solduri neîncasate" export (e.g. `neincasate.xls`) now imports. Two things changed vs. the original file.

- **Encoding fix** — the new export **mislabels its codepage** (declares cp1252 but stores Romanian Latin-2 bytes), which crashed `xlrd.open_workbook` with `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`. Parser now falls back to `iso-8859-2` when the default decode raises. The old file is unaffected (ASCII-safe). Header-name mapping already ignores unknown columns, so both export widths (26 vs 28 cols) go through the same path.
- **Data model** — migration **0034** adds four columns to `solduri_neincasate`: `discount` (%), `cec` (cheque flag 0/1), `scad_cec` (cheque due date — Excel serial parsed to ISO, junk `-   -` placeholders → NULL), `cec_doc` (cheque-associated document no, from the export's `_dl` column). Replace-only table, no backfill.
- **UI** — invoice view (`/solduri-neincasate?view=invoice`) gains two columns: **CEC** (badge when set) and **Scad. CEC**; these also flow to the invoice Excel export. Address/registry/driver/price-type columns present in the file were intentionally **not** captured (owner scope).
- Files: `etl/import_solduri_neincasate.py` (encoding fallback, generic Excel-date helper, 4 new fields), `migrations/0034_20260707_solduri_extra_cols.py`, `app/queries/solduri.py` (invoice SELECT), `app/templates/solduri_neincasate.html`. Verified against the real 1,763-row file: 99 cheques parsed with due dates, 328 discounts. Tests: 12 passing (1 new: `test_parse_new_format`, encoding + cheque-field assertions).

### P&L module relocated from standalone pnl_app into TorbApp (2026-07-07)

The standalone monthly P&L app (`pnl_app/`, own Flask + SQLite on port 5002) is now a native TorbApp module: auth-gated, shared sidebar nav + base template, single `torb.db`, migration runner, host dependencies. Straight relocation — no behavior changes. Design: `docs/specs/2026-07-07-pnl-module-integration-design.md`; plan: `docs/plans/2026-07-07-pnl-module-integration.md`.

- **Data model** — migration **0033** adds four `pnl_`-prefixed tables: `pnl_balante_raw`, `pnl_mapping_conturi` (seeded 33 account→line rows), `pnl_config` (seeded 9 alarm rows), `pnl_import_log`. Reference tables created + seeded on every environment; balance rows arrive via Excel upload. Data-layer notes: `docs/TECHNICAL.md` §Data.
- **Compute** (`app/pnl_logic.py`) — full monthly P&L for `torb`/`tobra`/`grup` (consolidated), YoY deltas, YTD subtotals, configurable alarms (delta warn/error, percentage thresholds, N-month deterioration trend). Monthly amount = `rulcd` delta vs. prior month. Reads via `app/queries/pnl.py`.
- **Import** (`app/pnl_import.py`) — Romanian `.xls` trial balances read with the host `xlrd` (no new dependency; nothing imported from `pnl_app/`). Folder scan + single upload; filename-driven entity/period detection.
- **Excel export** — styled workbook (3 entity sheets + KPI summary, alarm-colored) rebuilt as `build_pnl_xlsx` inside the shared `app/exports/excel_export.py`.
- **Routes** under `/pnl/*` (`app/blueprints/pnl.py`): year view, import page, alarm-config editor, scan/upload/save APIs, Excel export. Auto-protected by the host auth gate. Upload/scan failures surfaced via the shared `AppError.show()` modal. New `pnl_num` Jinja filter for the dense grid; percentages reuse the global `pct` filter. Sidebar link "P&L" after Profitabilitate.
- **Config** — `pnl_torb_folder`/`pnl_tobra_folder` in `app/config.py` (env-backed, folder-scan sources).
- Existing `pnl.db` data (1948 balance rows across 2025–2026) copied once into `torb.db` locally via a throwaway dev script (not committed); dev/prod load their own data through the upload UI. `pnl_app/` deleted. Tests: 278 passing (20 new across db/queries/logic/import/export/routes). Verified end-to-end against copied data (torb 2026 Mar: CA 1.39M, EBITDA 204k, Profit net 145k; workbook builds).

### Siguranță la reimportul zilnic Tobra: cohortă buggy ștearsă, chei de dedup stabile (2026-07-07)

Owner: the Tobra file is re-imported **daily** — the fixes must not reset or duplicate on each upload.

- Analysis: the daily import only ADDs rows (`INSERT OR IGNORE` on `nr_dl, cod_produs, nr_factura`), so migration fixes survive; and migration 0031 already aligned existing rows' `cod_produs` to the same Torb codes the fixed import computes, so re-imported lines dedup correctly. The one remaining hazard: rows renamed by the buggy July run for articles **without** prior Auchan history (unrepairable in place) keep a stale dedup key — the next daily upload would insert the correct row next to the wrong one (double counting).
- **Migration 0032** drops the buggy-run cohort (TOBRA rows dated ≥ 2026-06-01); the next daily upload re-inserts all of it through the fixed cod-mare pipeline. Runs once (versioned) — daily imports never re-trigger it. Daily-reimport property + corollaries documented in `docs/BUSINESS_LOGIC.md` §3.

### Import Tobra→Auchan: identitatea articolului pe COD MARE + istoric unificat în Stoc & Comenzi (2026-07-07)

Owner report (screenshot prod, Auchan Iul 2026): the July KL sales appeared as "C.Goplana Jeleuri" (Celmar) on Tobra codes 1508/1509, and Auchan's history was missing from the per-article view in Stoc & Comenzi. Owner rule: **cod mare is the article identifier for the Tobra import**.

- **Root cause**: the July import "normalized" SKU names via a `{cod_produs: sku}` lookup built from Torb ERP rows — but Tobra's numbering collides with Torb's, so the KL rows were renamed to the Torb article for the same numeric cod (C.Goplana) and misfiled under Celmar. Separately, Auchan rows kept Tobra's `cod_produs`, so Stoc & Comenzi (which aggregates `tranzactii` per `cod_produs`) never saw Auchan's history on the real article.
- **ETL** (`import_vanzari_tobra_auchan.py`): identity now comes from the cod mare embedded in the product name (`extract_cod_mare` + `build_cod_mare_lookup` — stoc `cod_mare` first, then the name-embedded code). On a match the row adopts the Torb ERP sku **and Torb `cod_produs`**; unmatched rows keep the Tobra name/cod verbatim. The Tobra cod survives as `cod_tobra` for the `corr_vanzari_tobra` cost lookup. The cod_produs-based rename is gone.
- **Migration 0031**: (1) un-renames the collision-hit rows (restores the historical Auchan sku/furnizor; a same-cod-mare pair = legitimate ERP rename, left alone), (2) aligns Auchan rows' `cod_produs` to the Torb ERP cod via cod mare — Auchan KL history now sits on articles 1661/1662/… alongside the other clients, and future-import dedup keys stay consistent.
- **Stoc & Comenzi article history** (`/api/forecast/sku-clients/<sku>` → `sku_clients_monthly`) aggregates over all SKU spellings of the article (`sku_variants`) — verified: KL Earl Grey queried by the ERP name now lists AUCHAN (13.680 buc) among its clients.
- Tests: 266 passing (cod-mare extraction incl. Leonex paren form, collision-proof identity resolution, migration repair + idempotency on a synthetic DB). Business rule documented in `docs/BUSINESS_LOGIC.md` §3 (Auchan/Tobra exception) + §5.

### Fix: catalog pe brandul corect + pagina de produs unificată pe denumiri (2026-07-07)

Owner report on articles 90204/90205 (KL Earl Grey / English Breakfast): a July KingsLeaf sale to Auchan wasn't visible. Root causes were the Tobra data-flow lag (sale sits under client Tobra until the monthly "Vânzări Auchan" import — by design) plus two real defects found while tracing:

- **Catalog (`produse`) brand**: the monitorizare spreadsheet lists KingsLeaf/Tipson articles with Furnizor=Basilur and the sub-brand only in the Brand column ('KINGSLEAF', 'TIPSON TEA'), so 54 KingsLeaf + 56 Tipson articles sat under furnizor='Basilur'. `import_preturi` now normalizes via the Brand column (`VIRTUAL_BRAND_CANON`, catches typos like 'KINSGELAF' and CHRISTMAS-named KL articles); migration 0030 backfills. Also fixed the dead `SUPPLIER_ORIGIN` key 'Kings Leaf' → 'KingsLeaf'.
- **Product page split per SKU spelling**: the same article exists under two tranzactii names (ERP 'KL CEAI EARL GREY 90204-...' vs Tobra/Auchan 'KL EARL GREY 90204-...'), so `/produs/<sku>` showed only half the history — Auchan was invisible on the ERP-named page. `queries.sku_variants` (built on `resolve_catalog_sku`) now aggregates the page, its KPIs, client tables and Excel export over all spellings of the same catalog article; the header lists the merged names.
- Verified in browser: the ERP-named KL Earl Grey page now shows brand KingsLeaf, combined KPIs (74.039 RON YTD 2026) and Auchan in Istoric (55.574 RON total). Tests: 261 passing.

### Fix: produsele HORECA ale sub-brandurilor virtuale rămân pe brandul lor (2026-07-07)

Owner rule: Basilur / KingsLeaf / Tipson / Organsia must always show separately, everywhere.

- The generic `HORECA ` → Basilur name rule ran before any virtual-brand check, so Tipson's HORECA line (`HORECA TS ...`, ERP 80xxx — 9 SKUs, ~5.8k RON) sat under Basilur in `tranzactii` and `produse`. All three ETL derivation functions (`import_stoc`, `import_vanzari_erp`, `import_vanzari_tobra_auchan`) now check `HORECA TS ` / `HORECA KL ` / `HORECA ORGANSIA` first; migration 0029 reclassifies existing rows across `tranzactii`/`stoc`/`produse` (idempotent).
- Docs: `docs/BUSINESS_LOGIC.md` §5. Tests: 261 passing (new coverage for the HORECA variants on all three derivers). Verified post-migration: zero family SKUs left under a wrong brand.

### Fix: branduri greșit atribuite la Auchan — KingsLeaf lipsea din raportare (2026-07-07)

Owner report: KingsLeaf never showed up as a separate brand in Auchan's client reporting/history.

- **Root cause**: the Tobra→Auchan import resolved `furnizor` through a `cod_produs` lookup built from Torb ERP rows, but Tobra's product-code numbering collides with Torb's (e.g. Tobra `1508` = *KL English Breakfast*, Torb `1508` = *C.Goplana*/Celmar). Result at Auchan: KingsLeaf tea filed under Celmar (135k RON) and Basilur (12k), Toras chocolate under Basilur (137k) and Solvex (6.6k), Celmar tea under Basilur (34k) — ~325k RON misattributed across 2024–2026.
- **ETL** (`etl/import_vanzari_tobra_auchan.py`): SKU-name prefix rules now run **before** the cod_produs lookup; the lookup remains only as fallback for names with no rule. Tests cover the collision case.
- **Migration 0028** re-applies the prefix rules to existing Auchan rows (idempotent, same rule order as the ETL). Verified after migration: KingsLeaf appears at Auchan with full history (70.080 / 56.749 / 20.089 RON on 2024/2025/2026) and zero mislabeled KL/T./CELMAR rows remain.
- Docs: `docs/BUSINESS_LOGIC.md` §5 records the lookup-fallback rule. Tests: 260 passing.

### Analiză: istoric clienți pe produs, taburi produse la client, cache-busting statice (2026-07-07)

Owner report: on the product page a client like Auchan "disappears" if it only bought in past years; the produse nelistate list sat below the sold-products table; filters looked dead in the browser.

- **Produs → Clienți: toggle Perioadă/Istoric** — the client table on `/produs/<sku>` only showed buyers in the selected period, hiding historic buyers entirely. New *Istoric* view (`queries.product_clients_istoric`) lists every client that ever bought the SKU with dynamic per-year Val Netă columns, totals and last-purchase date; the quick client search filters both views.
- **Client page: Produse Cumpărate / Produse Nelistate as tabs** — the two stacked cards became Bootstrap tabs; the Perioadă/Istoric toggle and column filters live inside the Nelistate tab unchanged.
- **Static cache-busting** — `url_for('static', ...)` now appends `?v=<mtime>`, so browsers pick up new JS/CSS right after a deploy. Likely the reason the (working) table filters appeared broken: `table-filter.js` reached prod on 2026-07-06 but stale cached assets kept the buttons dead until a hard refresh.
- **Period labels** — templates referenced undefined `period_cy`/`period_py` (headers rendered as "Val Netă  vs "); the context processor now derives them from `an`/`luna` ("2026", "Mar 2026").
- Tests: 258 passing. Verified in browser: Auchan visible in Istoric on a 2024/2025-only SKU; tabs + filters work on `/client/732`.

### Solduri: disjoint aging buckets + new terminology (2026-07-06)

Owner changed the aging rule and vocabulary, applied module-wide (cards, all three table views, client page, invoice category labels, Excel exports).

- **Buckets are now disjoint ranges** instead of nested/cumulative: **1-7 / 8-30 / 31-60 / >60 zile** on each side (keys `nesc7/nesc30/nesc60/nesc60p` + `scad7/scad30/scad60/scad60p`). Every document falls in exactly one bucket, so the 8 cards sum exactly to Total în piață — the "Neîncadrate" catch-all card is gone (its `>60` content now lives in the two `>60` buckets). Due today (d=0) still counts as in-term.
- **Terminology**: "Nescadent" → **"În termen"**, "Scadent" → **"Scadență depășită"** (per-invoice category label: "Depășit N zile"); the "Total scadent (toate restanțele)" card is now "Total scadență depășită".
- Client/agent views grew to 8 bucket columns; KPI rows of 4 cards per side. Old `?bucket=` links keep working for surviving keys (`scad30` etc. now mean the disjoint range).
- Files: `app/queries/solduri.py` (predicates, labels, bucket columns), `app/templates/solduri_neincasate.html`, `solduri_client.html`. Tests updated for disjoint sums + new reconciliation identity (258 passing). Domain rules: `docs/BUSINESS_LOGIC.md` §9.

### Pricing module F4+F5: article-creation sheets + supplier price updates with diff (2026-07-06)

Closes the phased plan (`docs/plans/2026-07-05-modul-pricing-ofertare.md` §5 — all phases delivered).

- **F4 — Fișă creare articole** (`/preturi/propuneri/<id>/fisa.xlsx`) — third download per proposal: the logistics/master-data sheet a client needs to list new articles. Templates: `auchan_creare` (key columns of Auchan's "Model propunere creare articol": Cod Tarifar, PCB, unit/case weights, case dims in meters, pallet count, VAT, origin — manual fields like Ingrediente/Alergeni left empty, exactly how the team completes the real file; auto-selected when the proposal's client name contains AUCHAN) and `generic` (all held master+logistics data incl. case dims in mm and CBM). Enriched export query now carries hs_code, origin, unit/case weights and dims.
- **F5 — Actualizare prețuri furnizor existent** (`/preturi/actualizare-preturi`) — upload the supplier's new official price list (any xls/xlsx, letter-mapped cod+preț columns), see the **diff** against current purchase prices (old/new, Δ%, last order price; unknown codes reported with a pointer to the offer import), tick what you accept, apply: `pret_achizitie_valuta` updated and landing recomputed keeping each row's existing currency/rate/transport/duty. Per owner decision #10 the official list is the source and the response **alerts** on every SKU whose new list price differs >1% from the last order price. Supplier codes resolve via SKU, `-00` suffix, or the last order's `cod_furnizor`.
- Catalog header gains *Actualizare prețuri*; proposals get the fișă button. Tests: 258 passing (4 new: both fișă layouts, diff→apply landing math + last-order alert, unknown-supplier guard). Verified in browser: all three exports (listare/ofertă/fișă Auchan) download from a real proposal.

### Pricing module round 4: prospect clients, potential articles, supplier offer import, product photos (2026-07-06)

Owner requests: offers for clients not yet in the ERP, articles not yet in stock (supplier portfolios / new-supplier price offers priced for Romania), photos from basilurtea.com for Basilur + manual upload for the rest.

- **Prospect clients** — "Client nou (prospect)" on the simulator registers a client that doesn't exist in `tranzactii` (`clienti_pricing`, generated code `PROSPECT-<n>`, generic listing template; same name → same code). Prospects appear in the client dropdown tagged `[prospect]`, get proposals, listings and offers like any client; name resolution in proposals/exports falls back from `tranzactii` to `clienti_pricing`.
- **Potential articles** — `produse.potential` (migration 0027) marks not-in-stock articles; created from `/preturi/nou` (checkbox) or imported. Tagged `potențial` in the simulator; priced and offered like regular articles.
- **Supplier offer import** (`/preturi/import-oferta`) — upload an arbitrary xls/xlsx price offer from a (new) supplier, preview the grid, map columns by letter (cod/denumire/preț + optional EAN/gramaj/buc-bax), set currency/rate/transport/duty → articles enter the catalog as potential with landing computed (`app/supplier_offer.py`). Existing SKUs are skipped and reported, never overwritten. Verified against the real Ipek order file (10/10 valid lines parsed).
- **Product photos** — photo card on `/preturi/<sku>`: file upload or image URL (downloaded server-side) → `app/static/product_images/<sku>.<ext>` + `produse_media` (`principala=1`, history kept). Basilur articles get a basilurtea.com product-search link for copy-pasting the image URL (owner: that site covers only Basilur; the rest is manual).
- Tests: 254 passing (4 new). Domain rules documented in `docs/BUSINESS_LOGIC.md` §10; data-layer notes in `docs/TECHNICAL.md` §Data.

### Pricing module F3: client xls files from proposals — listing templates + photo offer (2026-07-06)

- **`app/exports/listare_export.py`** — data-driven client file generation from a saved proposal. Layouts replicate the real files each retailer expects: `kaufland_modificare` (price-change form: cod articol/Kaufland, old/new list+invoice price, valabil de la), `selgros_lista` (vendor header block, UC/UV, case+unit list and net prices, EAN, pallet count), `fildas_lista` (cod furnizor, gramaj, old/new invoice price), `sezamo_lista` (client internal code), `generic` fallback. Template per client lives in `clienti_pricing.template_listare` (migration 0026 seeds Kaufland/Selgros/Fildas/Sezamo by name lookup, NULLs only — UI-set values win).
- **Offer with photos** — `build_oferta`: product photo thumbnails (~96px, Pillow) embedded per row from `produse_media` (local path, or `url_sursa` downloaded once into `app/static/product_images/` with a 5s timeout), gramaj, buc/bax, EAN, price without/with VAT.
- **Routes** `/preturi/propuneri/<id>/listare.xlsx?template=&valabil=` and `/preturi/propuneri/<id>/oferta.xlsx?valabil=` (attachment download, filename includes client + validity date). Simulator proposals card gains a *Valabil de la* date picker, a *Format* override selector and per-proposal download buttons.
- `queries.propunere_linii_export` enriches proposal lines with product, logistics, per-client internal codes and the main photo. Tests: 250 passing (5 new: per-template layouts incl. Selgros case-price math, template override, generic fallback, VAT math in the offer). Verified in browser: Kaufland proposal (22 lines) → both files download with the auto-selected template.

### Pricing module F2: price simulator, proposals, manual article creation, seed data to dev (2026-07-06)

- **Simulator** (`/preturi/simulator`) — pick a client, see every article with a landing cost (landing, current price, effective conditions %), type proposed prices or bulk-apply a target NET margin / % increase over current price to the filtered rows; net margin recomputes live and is colored by the configured thresholds. Save as a named proposal.
- **Proposals** — `propuneri_pret`(+`_linii`, migration 0025): margins and threshold verdicts are recomputed **server-side** via the pricing engine at save time (client input is only sku+price); list with "sub prag aprobare" counter, detail view with per-line verdict badges, delete (cascade). Foundation for F3 offer/listing generation.
- **Manual article creation** (`/preturi/nou`) — full form: master data (datalists from existing values), optional purchase price (landing computed with the standard formula), optional logistics (carton CBM auto-computed from dims), optional photo URL (`produse_media`). Covers the 90 unmatched SKUs from the F0 report until the full F4 flow (client sheets) lands.
- **Seed data migration 0024** — the locally-validated pricing rows (1013 landing costs, 968 prices incl. 334 per-client, 268 client codes, 44 logistics rows, 6 condition totals, 7 clients) travel to dev/prod via `migrations/data/0024_pricing_seed.json`, since the source Excels are gitignored and there is no SSH path. INSERT OR IGNORE: existing rows on the target DB always win; skipped entirely on an empty catalog (test DBs).
- Catalog header gains *Simulator preț* and *Articol nou* buttons. Tests: 245 passing (6 new F2 route/API tests). Verified in browser: Auchan simulation over 1013 articles, 30% net target on 33 filtered articles, proposal saved/viewed/deleted.

### Pricing module F1: cost/margin engine + net margin per client (2026-07-06)

- **`app/pricing_engine.py`** — pure, tested margin math: landing cost, margin-of-price convention (48.3 → 69 = 30%), `pret_pentru_marja` (target NET margin + conditions), `marja_neta_pct`, `verdict` against thresholds, `praguri_marja` (from `pricing_config`, per-gama override → global), `cond_effective` (sums `conditii_comerciale` rows with NULL-wildcard scope on client/furnizor/categorie/sku — deliberately independent of `cond_resolved`, whose supplier keys come from the ERP spelling, see BACKLOG #13).
- **`/preturi/<sku>`** — the per-client price table gains *Condiții %* and *Marjă netă %* columns; net margin is colored by the configured thresholds (≥30% green, 25–30% yellow, <25% red + "necesită acordul directorului" warning). Verified in browser on SKU 534: Auchan 32.6% gross − 11.72% conditions = 20.8% net flagged red.
- **Importer additions** — per-client current invoicing prices from FISIER_CONSOLIDAT (`Pret facturare actual <client>` columns → `preturi_vanzare`, 334 rows, fill-missing-only) and `--seed-conditii` (CONDITII sheet totals → one pct row per client marked "de defalcat", 6 clients seeded; `cond_resolved` truncated for lazy rebuild).
- **Migration 0023** — `preturi_vanzare` standard rows (cod_client NULL) deduped (289 SKUs had stacked duplicates: SQLite UNIQUE treats NULLs as distinct, so INSERT OR REPLACE never replaced them) + partial unique index `idx_pv_standard_unic` so upserts work from now on.
- Tests: 239 passing (8 new engine tests).

### Pricing module F0: data foundations + one-off import (2026-07-06)

Owner request 2026-07-05: pricing module from purchase price → landing cost → margin simulation per client → offers with photos → per-client xls listing files. Strategy + owner decisions: `docs/plans/2026-07-05-modul-pricing-ofertare.md`.

- **Migration 0022** — `produse_logistica` (unit/carton dims, weights, CBM, units/case), `produse_media` (product photos: local path and/or source URL), `coduri_client_articol` (per-client internal article codes), `pricing_config` (margin thresholds as data — global 30% min / 25% approval floor, per-gama override), `clienti_pricing` (simulated shelf margin, listing template key); `conditii_comerciale` gains optional `categorie`/`sku` scope.
- **`etl/import_pricing_f0.py`** — imports FISIER_CONSOLIDAT_PRETURI.xlsx (268 client codes for Auchan/Metro/Kaufland/eMAG/Supeco/Carrefour, 48 missing purchase prices) and Basilur RO1 order forms (44 SKUs with carton dims/CBM/weights; cm→mm conversion validated against the CBM column). Existing DB prices are never overwritten — differences go to a data-quality report (`Date pricinng&Logistica&Ofertare/rapoarte/f0_import_raport.txt`): 51 price differences, 90 unmatched SKUs, conditions gap vs `cond_resolved`.
- Commercial data folder added to `.gitignore` (xls sources never land in git). Tests: 231 passing.

Owner request: easy navigation agent → clients → invoices on the Solduri page.

- **New client page** `/solduri-neincasate/client/<codcli>` — header cards (sold total, total scadent, zile restanță max, plafon with over-ceiling badge), contact strip (agent — linked back to the agent's client list —, telefon, canal, open-document count) and the full list of the client's open invoices: data emiterii, scadență (derived `datadl + term_pl_cl`), termen, sumă, zile (overdue shown as "N întârziere" in red), aging category, plus a total footer. Excel export of the invoice list (`?view=invoice&codcli=`); a **Fișă client (vânzări)** button cross-links to the analytics client page when the ERP code exists in `tranzactii`. 404 on unknown code.
- **List page links** — client names in the *Client* and *Factură* views link to the client page; agent names in the *Agent* and *Client* views link to `?view=client&agent=` (bucket filter preserved), so card → agent → client → invoices is fully clickable.
- Plumbing: `queries.solduri_client_header()`, `codcli` filter on `solduri_by_invoice()` (+ `codcli` column in its output/export), `codcli` passthrough in the blueprint's `_params`/`_load`. New template `app/templates/solduri_client.html`. Tests: header aggregates, per-client invoice filter, route + export smoke (230 passing).

### Hotfix: adding a new export country failed at the DB level (2026-07-04)

- `tari_export` still carried `CHECK(piata IN ('RO','HU'))` from migration 0001, blocking the new data-driven multi-country model at INSERT time — **migration 0020** rebuilds the table without the CHECK. The `/forecast/setari` country form also swallowed API errors (reloaded on any response); it now surfaces them via `AppError.show()`. Verified end-to-end (Bulgaria/BG → dynamic Sug. BG column).

### New module: Solduri neîncasate (accounts-receivable aging) (2026-07-05)

New **Comercial → Solduri** page turning the ERP receivables export into an aging dashboard.

- **Data source** — the consolidated ERP report (`neinc … .xls`, one row per open document; sample `docs_input/rapoarte/neinc 30 06.xls`, 1,683 rows). Outstanding amount is `sumdeincas` (may be negative — advances/credit notes). Due date is **derived** as `datadl + term_pl_cl` (the file's `scadenta` column only holds the term in days), never read from the file.
- **Ingestion** — reuses the existing async upload pipeline: `tip='solduri'` added to `app/blueprints/actualizare.py` (whitelist + `script_map`); new `etl/import_solduri_neincasate.py` (xlrd) parses and **replace-loads** the new `solduri_neincasate` table (**migration 0021**), stamping `data_raport` = upload date. An upload widget lives on the page (posts to `/api/upload/solduri`, reuses `upload_jobs`/status polling).
- **Aging math** — reference = today (owner decision). Per row `d = zile până la scadență` (negative = overdue); every row incl. negatives is bucketed by `d` so the cards + catch-all reconcile exactly to Total în piață. Cards: **Nescadent** ≤7/≤30/≤60 (nested), **Scadent** ≤7/≤30/≤60 (nested), **Total scadent** (all overdue), **Total în piață**, and a **Neîncadrate** catch-all (>60 zile viitor / restanță). Verified on real data: total în piață 3,163,823.97 lei, reconciliation exact.
- **Table** — three view modes (`?view=`): per **client**, per **agent** (both with per-bucket columns, oldest-overdue days, plafon over-ceiling flag), and flat per **factură** (sortable by scadență). Clicking any aging card filters the table to that bucket (`?bucket=`), scoping the shown totals to the clicked card; agent + client-search filters; Excel export of the current view.
- Files: `app/queries/solduri.py`, `app/blueprints/solduri.py`, `app/templates/solduri_neincasate.html`, nav link in `base.html`. Tests: `tests/test_solduri.py` (ETL parse incl. negatives, bucket sums + boundary + reconciliation identity, view shaping/filter, route+export smoke). 229 passing. Spec `docs/specs/2026-07-05-solduri-neincasate-design.md`, plan `docs/plans/2026-07-05-solduri-neincasate.md`.

### Forecast finalized: client × article is now the default; legacy model, compare & velocity toggle removed (2026-07-05)

Owner GO after dev validation. The client × article model is now the **only** forecast model; the transitional scaffolding is gone.

- **Legacy `actual` model deleted** — `forecast_logic._monthly_sales_by_sku` and `_ro_hu_split` removed; `build_suggestion` and `queries.forecast_stoc_extended` lost their `model` parameter and now always run the pair engine. `?model=nou`/`?model=actual` and the `?compare=1` view (route branch, `suggested_ro_nou`/`Δ RO` columns, the "Model actual / Model nou" and "Comparație" buttons) are all removed from `app/blueprints/forecast.py` and `forecast.html`.
- **`3 ani / 90 zile` velocity toggle removed** — `forecast_stoc_extended` lost its `vel` parameter; Vânz./lună + Zile stoc on the page **and** the Excel export now always compute on the seasonal mean over the configured `fereastra_luni` window (Setări forecast). The Excel export also emits one `Sug. <țară>` column per active export market (was fixed `Sug. HU`).
- **Decision 9 (RO/export split)** — confirmed **implemented** as the multi-country columns (Sug. RO + one per export market); dropped from the open list.
- **Decision 11 (price-diff alert)** — set to **1%**, stored as `prag_alerta_pret_pct` in `forecast_config` defaults (`app/forecast/config.py`) and editable on `/forecast/setari`. No consumer yet — dormant until the receipt price-alert (F2) lands, so it's configured rather than hardcoded.
- **Decisions 6, 12, 13, 14 → backlog** — MOQ (6), dead-stock + ERP lot/BBD report (12+13, one implementation), and a new **"Notifications"** umbrella (14). See `docs/BACKLOG.md` §Aprovizionare — planned components. `app/templates/decision_torb.html` + `testing_checklist.html` updated to reflect all 14 decisions as resolved or scheduled.
- Tests updated for the single-model world: velocity/compare/model-param tests removed or repointed; `test_ro_hu_split` migrated to `split_with_safety` (coef=0); a stale `zile_stoc` fixture refreshed with recent sales (the pair engine now correctly marks a 2025-only SKU INACTIV). 222 passing.

### Owner feedback round: forecast visibility, setari UX, nelistate fix (2026-07-04)

Six-item owner list (evaluated on dev :5001). Items delivered:

- **Suspects list on click (item 1)** — the "Suspect delistare" badge (Stoc + Sugestie tabs, `?model=nou`) now opens a `modalSuspects` dialog listing the clients excluded from the article's forecast: name, ERP code, SUSPECT/DELISTAT status, days since last order, mean order interval. Plumbing: `suspects`/`inactive` propagated through `forecast_stoc_extended` (all 3 row sources) and `build_suggestion`.
- **INACTIV visible in the new stock model (item 4)** — grey `INACTIV` badge on Stoc/Sugestie rows when the pair-engine cut zeroes an article's forecast (was computed but never displayed).
- **Client typeahead on /forecast/setari (item 6)** — the add-client-to-country modal now searches existing clients by name/code as you type (`/api/clienti/search`, debounced) and auto-fills the ERP code on selection — no more looking up codes by hand.
- **Forecast params explained + 3 missing tunables (item 5, UI part)** — every parameter on the "Parametri forecast" card gained a plain-Romanian description; `confirmare_delistare_zile`, `taiere_inactiv_luni`, `prag_neutru_multi_client` (previously DB-only) are now editable in the card. The 36→24-month window change itself is data (owner sets it in the card), not code.
- **Produse-nelistate section actually works now (item 3)** — root cause wasn't the column filters: `produse.sku` formats differ per supplier (verbatim names for Cosmetice, `<code>-00` for Basilur, EAN-keyed for others), so the `p.sku NOT IN (SELECT sku FROM tranzactii ...)` exclusion matched nothing — the section always listed the entire catalog (identical Perioadă/Istoric lists), company Val Netă/Nr. Clienți stayed 0 for most rows, and a multi-price join duplicated 109 rows. New shared `queries._shared.resolve_catalog_sku()`/`get_catalog_resolver()` (verbatim → stoc cod_mare → `<code>-<EAN>` tail → bare EAN) now powers exclusion, company stats, and the display code; price join deduplicated. Validated on real data (client 1263: Perioadă 1295 vs Istoric 1279, 16-product win-back delta, 0 dupes). Tests: `tests/test_catalog_resolver.py`, `test_forecast_routes.py` (+8 total).
- **Multi-country export model (item 2)** — the binary RO/HU split becomes fully data-driven multi-country. Countries are defined only in `/forecast/setari` (`tari_export.piata` is now a free short code — RO keeps the "domestic bucket" meaning); clients allocated to a non-RO country are excluded from the RO suggestion and forecast under their country. `pair_engine` resolves each client's market from the DB (no names/countries in code) and emits per-country monthly profiles (`piete`); `split_with_safety(monthly_piete=...)` implements the owner's stock rule — **available stock covers RO only, each export country orders its full coverage demand + safety** (legacy surplus-offset behaviour retained for `model=actual`). UI: the Stoc tab renders one editable "Sug. <țară>" column per active country; the Sugestie tab shows per-country breakdowns inside the Export cells; the add-to-order modal grows one quantity field per country. Orders persist the per-country split in the new `comenzi_linii_piete` table (**migration 0019**, owner decision: persisted, not display-only) with `cantitate_export` kept in sync; `comanda_get` returns `cantitati_piete` per line. From the Sugestie bulk save, the breakdown is stored only when the ordered export qty equals the suggested sum (an edited aggregate can't be allocated honestly). Tests: `tests/test_multi_country_export.py` (profiles, no-offset split, legacy mode, order round-trip).

### Forecast: spec-completion engine pieces (neutral months, INACTIV, DELISTAT, MOQ floor) (2026-07-04)

Low-risk, fully-specified parts of the owner spec/brief, all pure + unit-tested and wired only into the `?model=nou` path (default stays legacy — validate via `?compare=1` before flipping).

- **Neutral months (Brief §4.1, level 1)** — `pair_engine.neutral_months`: a month where ≥ `prag_neutru_multi_client`% (default 70) of an article's covering clients sold zero is treated as a supply-gap and excluded from every pair's mean (distinguishes "nobody could buy" from "demand fell"). Requires ≥2 covering clients so single-client churn can't trip it.
- **Global INACTIV cut (Spec §7)** — `pair_engine.is_inactive`: zero total sales across the last `taiere_inactiv_luni` (6) closed months → article forecast 0; neutral months don't count as evidence, and strongly seasonal articles (peak seasonal index ≥ 3.0) are never auto-inactivated.
- **DELISTAT label (Spec §5.2)** — `delisting_status` gains `confirm_days`: a SUSPECT pair auto-labels DELISTAT past `prag + confirmare_delistare_zile` (90). Same numeric effect as SUSPECT (contribution 0) — label only, for reporting (`n_delistat`).
- **MOQ floor (Spec §8)** — `forecast_logic.split_with_safety(..., moq=None)` applies `max(brut, MOQ)` before bax rounding, never lifting a zero need into an order. Inert until MOQ data exists (`produse` has no MOQ column).
- **Daily stock-snapshot capture** — new `etl/snapshot_stoc.py` copies the latest `stoc` snapshot into `stock_snapshot` (idempotent per date) so OOS history accrues for level-2 later. `stock_snapshot` survives the partial rebuild; open item is wiring the run into `rebuild_db.main()` / a scheduled job.
- Config: migration `0018` seeds `prag_neutru_multi_client` (70). Owner decisions cross-referenced in `app/templates/decision_torb.html` (1–10 resolved by the docs; 6/9/11–14 open). Plan + spec digest: `docs/plans/2026-07-04-forecast-spec-completion.md`. Tests: `tests/test_pair_engine.py`, `test_forecast_reorder.py` (+8).

### Forecast: client × article demand model, behind a toggle (2026-07-04)

- New `app/forecast/pair_engine.py` computes demand per `(client, article)` pair instead of averaging a SKU across all clients: adaptive per-pair window (first sale → 36 months), monthly mean with zero-filled no-sale months (declining pairs decay to 0), article-level seasonal index gated at ≥24 months of history and clamped to `[0.2, 5.0]`, and an adaptive delisting `SUSPECT` flag when a pair's gap since last purchase exceeds `max(180 days, 3× its mean order interval)` (its contribution then drops to 0). Directly addresses backlog **B4** (delisted/declining SKUs kept being reordered).
- Order formula (partial): `forecast_logic.split_with_safety` adds `safety = coef × monthly forecast` (default 0.25) and rounds up to the supplier bax (`produse.buc_cutie`); MOQ floor deferred (`app/templates/decision_torb.html` item 6).
- Tunable parameters in a new `forecast_config` table (migration `0017`) + `app/forecast/config.py`, edited on a "Parametri forecast" card at `/forecast/setari`.
- Wired behind `?model=nou` in `build_suggestion` (Suggest tab) and `forecast_stoc_extended` (Stoc tab); the default `?model=actual` path is unchanged. `?compare=1` shows both models side by side (Δ columns) for owner validation before the default flips. UI: model toggle, "Suspect delistare" badge, seasonality "fără ajustare (<24 luni)" marker, suggestion-breakdown popover.
- Deferred spec items (§4.4 out-of-stock months, §5 full DELISTAT/REACTIVAT lifecycle, §6 new-listing ramp-up, §8 MOQ, §10 recompute cadence) await owner decisions — `app/templates/decision_torb.html` items 5–10.
- Spec: `docs/Specificatie Forecast Torb.docx`. Documented in `app/forecast/README.md`, `docs/BUSINESS_LOGIC.md` §7.1, `docs/TECHNICAL.md` §Data. Tests: `tests/test_pair_engine.py`, `test_forecast_reorder.py`, `test_forecast_config.py`, `test_forecast_routes.py`.

### Central logging config — rotating app + error logs, quieter werkzeug (2026-07-04)

- New `app/logging_config.py` (`setup_logging()`, idempotent) attaches two rotating file handlers to the root logger: `logs/app.log` (all levels per `LOG_LEVEL`, default INFO; 2 MB × 5) and `logs/errors.log` (ERROR-only; 1 MB × 3). `create_app()` routes through it.
- Noisy third-party loggers (`werkzeug`, `httpx`, `urllib3`) raised to WARNING so `app.log` isn't flooded with per-request `200 -` access lines; genuine 4xx/5xx still surface. Console echo only when `FLASK_DEBUG` is set.
- Documented in `docs/TECHNICAL.md` §Application logging.

### Forecast page — velocity-basis toggle aligning screen ↔ Excel (2026-07-03)

- `/forecast` Stoc tab: a `3 ani / 90 zile` segmented toggle next to Export switches the basis for the displayed `Vânz./lună` + `Zile stoc` columns (urgency badge + sort follow from `Zile stoc`); `Sug. RO/HU` stay on the seasonal model. Excel export now runs off the same `forecast_stoc_extended(vel=)` data as the page (and honours the search filter), so screen and Excel match for the selected mode. Default `3 ani` (prior behaviour). Resolves the page-vs-Excel velocity divergence as a runtime choice.

### Forecast page — order-status vocabulary, FK cascade, re-importable export (2026-07-03)

- Order-status vocabulary normalised (migration `0016`): legacy capitalised statuses folded (`Emisa`/`Confirmata`→`confirmata`, `In tranzit`→`in_tranzit`, `Receptionata`→`livrata`); `comanda_update` rejects an empty/whitespace status (still applies other fields) so the modal can't write `status=''`; all transit `IN(...)` lists standardised to `('confirmata','in_tranzit')`.
- `PRAGMA foreign_keys=ON` on app connections so `ON DELETE CASCADE` works (deleting an order removes its lines instead of orphaning them).
- New `— Cantitate comandată` column in the order Excel export so the export → edit → re-import round-trip works.
- Removed dead `forecast_stoc()`; extracted the shared `_ro_hu_split()` used by `build_suggestion` + `forecast_stoc_extended` (numerically identical before/after). Tests: `test_order_status.py`, `test_comanda_excel_roundtrip.py`, `test_ro_hu_split.py`.

### Forecast page — 10 P0/P1 fixes (2026-07-03)

- Restored the dead Export HU split (`clienti_export.cod_client` `BRANDMIX`→`1429`, `HUNTRADE`→`1430`, + validation when adding a client code); KPI cards count distinct SKUs not lots; `Zile stoc` excludes in-transit stock; transit ETA prefers `costuri_landing.eta`; export-code query made SQL-injection-safe; `_listing_changes()` keys normalised to match `build_suggestion()`; "Confirmă Comanda" excludes filter-hidden rows; `escapeHtml()` applied across client-side HTML building; removed dead `/api/comenzi/<id>/avanseaza`. Plan: `docs/plans/2026-07-03-forecast-p0-p1-fixes.md`. Tests: `test_forecast_queries.py` + 3 in `test_flask_routes.py`.

### Leonex order import — map supplier codes to Cod TORB (2026-07-03)

- New `corr_leonex_cod_mapping` table (migration 0014, mirrored in `etl/rebuild_db.py`) mapping Leonex supplier codes (`MK…`) to Torb internal codes (`cod_mare`), seeded with 10 pairs
- `etl/import_comenzi_tranzit_leonex.py` now resolves `MK → cod_torb → stoc.sku` and stores each order line under the Torb identity, so in-transit orders merge into the correct product row in the stock/orders view instead of surfacing as stray MK-coded rows
- Unmapped codes are skipped and reported (`AVERTISMENT:` line → amber note in the upload UI); upload job surfaces the warning via a new `avertisment` field
- Documented in `docs/BUSINESS_LOGIC.md` §8 and `docs/TECHNICAL.md` §Data

### Documentation reorganization (2026-07-02)

- Consolidated all project documentation into four category files under `docs/`:
  - `docs/BUSINESS.md` — company profile, market research, risks, AI opportunities, and the full 2026–2030 strategic plan (absorbs `context/` torb_background, project_business_overview, key_facts, project_key_risks, project_ai_opportunities, ai_optimization_report_1, glossary business sections, plan_strategic_5ani)
  - `docs/BUSINESS_LOGIC.md` — domain vocabulary, data model, transaction anatomy, bonus calculation, virtual brands, stock sync, forecast pointers (absorbs `context/glossary.md` data sections + `.claude/project_knowledge.md` feature sections)
  - `docs/TECHNICAL.md` — data layer, input-file map, deploy pipeline, VPS infrastructure, Romanian encoding rules, Typst manual rules (absorbs `.claude/project_knowledge.md` + `context/infrastructure.md` + `context/reference_data_files.md`)
  - `docs/BACKLOG.md` — tech-debt, infrastructure pending items, forecast audit findings, product/AI opportunity backlog
- `context/infrastructure_history.md` → `docs/TECHNICAL_history.md` (write-mostly archive, unchanged)
- `context/` now holds only the live `STATUS.md`; `.claude/project_knowledge.md` deleted (content redistributed)
- `CLAUDE.md` routing table updated to the new layout; working preferences consolidated from Claude session memory
- Path references updated in `README.md`, `.env.example`, `etl/backup_db.py`, `app/app.py`, `context/STATUS.md`
- Stale status fixed: bonus module marked delivered (was still listed as blocked), margin-audit deadline marked overdue
- Compiled manual PDFs moved from `docs/` root to `docs/manuals/*.pdf` (flat); Typst sources remain in gitignored per-manual subfolders — compile convention updated in `docs/TECHNICAL.md` §Typst
- `docs/superpowers/` dissolved: plans → `docs/plans/`, specs → `docs/specs/` (still gitignored); AI-workflow outputs now go directly under `docs/` (rule added to `CLAUDE.md`)

### Business constants centralised + true Torb cost on Auchan sales (2026-07-02)

- New `app/business_constants.py` (Auchan/Tobra exception: agent, client codes, invoice prefix, 30-day cost window), used by `import_vanzari_erp.py` + `import_vanzari_tobra_auchan.py`. New `corr_vanzari_tobra` table (migration 0013): Torb→Tobra lines (code 719) are diverted there at ERP import instead of dropped. The Auchan import overrides `pret_cumparare` with the 30-day simple mean per `cod_produs` at each row's date and recomputes `val_achizitie`/`marja_bruta`. Load order: ERP sales before Auchan sales.

### Forecast page audit — analysis only (2026-07-02)

- `docs/analysis/forecast_page_analysis.md`: architecture of the 5 tabs + AI agent, both suggestion algorithms, a column-by-column Stoc-tab reference, the full API, and 20 ranked issues — fed the P0/P1 and second-wave fix batches above.

### Organsia — fourth Basilur virtual brand (2026-07-01)

- `B.ECO ORGANSIA*` (ERP) / `ORGANSIA - …` (price list) products, previously mislabelled `Basilur`, get a prefix-derivation rule in the three ETL modules + a `produse` override in `import_preturi.py`, plus a 120-day lead-time seed (migration `0012`) with historical backfill (~20 stock, ~718 transactions, 11 products). Organsia now appears as the fourth brand in the Basilur report (Excel + PPT, colour `#6f42c1`), the bonus/post dropdowns, and AI prompts. Virtual-brand logic in `docs/BUSINESS_LOGIC.md`. Test: `test_derive_furnizor.py`.

### Monthly bonus engine redesign (2026-06-16)

- Config-driven bonus module (`feat/bonus-redesign`): per-agent monthly targets (sales, margin, 9 individual ranges, client count, new-clients-per-range, collections, scriptic), configurable weights + bonus value, a payout grid with thresholds (80% gate), a default +20% vs the same month last year, a month-close flow with a frozen snapshot, and agent management from the UI. Tables `bonus_config`, `bonus_lunar_config`, `bonus_obiective_strategice`, `bonus_payout_grid`, `bonus_istoric` (migration 0011). Pages: `/bonus`, `/bonus/obiective`, `/bonus/inchidere`, `/bonus/config`, `/bonus/clienti-noi-gama`.

### Database backup & restore — production (2026-06-11)

- `app/backup_db.py` (SQLite online-backup API, gzip, retention 15 days / min 3) + CLI `etl/backup_db.py` (backup/list/restore). Trigger: daily cron 02:30 on the prod VPS + automatic pre-deploy backup in CI before migrations. Admin page `/admin/db`: list, manual backup, download, restore with a typed "RESTORE" confirmation (auto safety backup + re-apply migrations). `PRAGMA busy_timeout=5000` added to `app/db.py`.

### Connection status served from server-side cache (2026-06-11)

- `connection_status` table (migration 0010) + `app/connection_cache.py` (3-min TTL) — at most one external eMAG/Shopify API call per platform per window, shared across all users. `connection-test` routes unchanged in URL/shape (new fields `cached`, `checked_at`); the connDot tooltip shows the check time.

## [0.6.0] - 2026-06-10

### Stock sync — history and eMAG sync

- Added unified sync history for both platforms: `shopify_sync_sessions` + `shopify_sync_rows` tables (migration 0006), then `platform` column added (migration 0007) — single table pair tracks sessions for both eMAG and Shopify
- Sync history panel on `/stocuri` shows last 10 sessions per platform (date + filename); clicking a session and pressing *Incarca date istorice* loads a read-only historical view of that sync
- eMAG sync history endpoints: `GET /api/stocuri/emag/sync-history` and `GET /api/stocuri/emag/sync-history/<id>`
- eMAG sync now persists session + row results identically to Shopify
- User audit on stock syncs: `sync_sessions.user_id` (migration 0008) records who ran each eMAG/Shopify sync (shown in the `/stocuri` history); tables renamed `shopify_sync_*` → `sync_sessions`/`sync_rows` (migration 0009, prefix obsolete now that sync is multi-platform)
- Shopify stock sync integration (GraphQL Admin API 2025-04, OAuth client credentials); unified `/stocuri` page with an eMAG/Shopify radio switch (delivered 2026-06-03)

### Project structure

- Moved `docs/plan_strategic_5ani.md`, `docs/STATUS.md`, `docs/torb_background.md` → `context/` (git history preserved via `git mv`); `docs/` now holds only implementation plans, analysis, specs, and user manuals
- Updated all path references in `CLAUDE.md`, `README.md`, `context/STATUS.md`
- Added `docs/manuals/` for end-user documentation (Typst source + compiled PDF); `.gitignore` updated to version only `.pdf` files from that tree

### Documentation

- Added `docs/manuals/stock/manual_stoc.typ` — Romanian user manual for the Sincronizare Stoc feature (eMAG + Shopify); compiled to `manual_stoc.pdf`

### Fixes

- `README.md`: corrected eMAG API version (v3 → v4.5.1), updated test count (66 → 73)

## [0.5.0] - 2026-06-04

### Technical Debt — Phases 1, 2, 3

- Deleted `etl/init_forecast_tables.py` (dead code — broken DB path, schema superseded by migrations 0001 + 0004)
- Updated default AI model in `app/config.py` from retired `claude-opus-4-7` to `claude-sonnet-4-6`
- CI/CD: added explicit `python migrations/runner.py data/torb.db` step before `systemctl restart` — failed migrations now abort deploy rather than crashing the running app
- Tests: replaced 289-line hand-maintained schema in `tests/conftest.py` with `migrations.runner.run_all()` — test schema is always in sync with production schema automatically
- Refactored `app/queries.py` (3,236 lines) into `app/queries/` package with 9 domain modules (`_shared`, `analytics`, `clients`, `products`, `pricing`, `orders`, `forecast`, `bonus`, `export`); `__init__.py` re-exports all names — zero callsite changes required
- DB cleanup (earlier in session): deleted orphan `clienti_export_old` table (migration 0005), moved forecast tables to migration 0004, removed dead `db_stock.py` + `data/stock.db`
- Documentation: corrected `CLAUDE.md` file paths (STATUS.md, plan_strategic_5ani.md moved to `docs/`), updated `README.md` test count, refreshed `docs/STATUS.md` (45 days stale), updated `context/project_ai_opportunities.md` (Shopify delivered)

### Comprehensive code audit (2026-05-28)

- Four parallel audit agents (backend, frontend, infrastructure, AI modules). Applied: env-controlled `SESSION_COOKIE_SECURE` + `LOG_LEVEL`, a 500 error handler, auth-gate fix for blueprint statics, open-redirect mitigation, `import_stoc.py` path fix, 10 MB upload check, dynamic filenames in the orchestrator, `BadRequestError`/`APIStatusError` handling in `ai_suggestions`, JSON error logging in the campaign/auto-post generators, light theme with dark sidebar, collapsible nav (localStorage), Trendyol packages template.

## [0.4.0] - 2026-05-23

### Authentication
- Added `app/auth.py` — two Flask Blueprints (`/auth`, `/admin`), `User` model (UserMixin), Flask-Login `LoginManager`, Flask-WTF `CSRFProtect`, in-memory rate limiter (10 attempts / 15 min per IP), auth audit log writer, SMTP email sender with graceful degradation
- Login/logout with "Remember me" (8h session, 7d cookie), redirect-back-after-login via `?next=`
- Forced password change flow: `force_pw_reset=1` redirects user to change-password before reaching any other page
- Password reset via email: SHA-256 hashed one-time token, 1h expiry, email enumeration prevention (always shows "sent" message); degrades gracefully when SMTP is not configured
- `require_role(*roles)` decorator for role-based access control; `before_request` guard protects all routes globally — API routes return `401 JSON`, page routes redirect to `/auth/login`
- `app/app.py`: `SECRET_KEY` from env, session/cookie config (`SameSite=Lax`, `HttpOnly`, `Secure=False` for HTTP VPS), `WTF_CSRF_CHECK_DEFAULT=False` (FlaskForm handles CSRF per-form; all existing API routes unchanged)
- `403.html` template and `@app.errorhandler(403)` (JSON for `/api/*`, HTML for pages)

### Admin UI (`/admin`)
- User list with role badges, status, last login
- Create user: generates random temp password displayed once, sets `force_pw_reset=1`
- Edit user: username, email, role, active/inactive toggle
- Admin-initiated password reset: new random temp password displayed once
- Toggle active/inactive (cannot deactivate own account)
- Admin nav item visible only to users with `role='admin'`

### User dropdown in navbar
- Username + role display, change-password link, logout — visible on all authenticated pages
- CSRF meta tag added to `base.html` for future JS use

### Migration `0002_20260523_add_auth`
- Creates `users`, `password_reset_tokens`, `auth_log` tables
- Seeds initial admin: username `admin`, email `vlad.rosioru@gmail.com`, `force_pw_reset=0`

### Dependencies
- Added `flask-login>=0.6`, `flask-wtf>=1.2` to `requirements.txt`
- `.env.example` updated with `FLASK_SECRET_KEY` and `SMTP_*` variables

### Tests
- `tests/conftest.py`: added auth tables to test schema, seeded test admin user, `client` fixture auto-logs in for the session
- All 61 tests pass with authentication enabled

## [0.3.0] - 2026-05-23

### Database migrations
- Introduced versioned migration system: `migrations/` folder at project root
- `migrations/runner.py` — standalone runner; applies pending migrations in `NNNN` order, records each in `schema_version` table; callable as CLI (`python migrations/runner.py [db_path]`) or imported by Flask at startup
- `migrations/0001_20260523_initial.py` — baseline schema (all 20+ tables, views, seed data, status normalisation) converted from the old `apply_migrations()` function
- Naming convention: `NNNN_YYYYMMDD_description.py`
- `schema_version` table tracks applied versions with timestamp; runner is idempotent and safe to run against existing databases
- `app/migrate.py` replaced with a thin wrapper (`apply_migrations()` → `run_all(DB_PATH)`) — `app/app.py` unchanged
- Deployment pipeline now runs `python migrations/runner.py data/torb.db` before `systemctl restart`; a failing migration aborts the deploy and leaves the running service intact

## [0.2.0] - 2026-05-23

### Code quality
- Fixed all 68 ruff linter errors across `app/` and root ETL scripts (E401, E402, E701, E702, E722, E741, F401, F541, F841); re-enabled lint job in CI pipeline

### Project structure
- Reorganized 29 root-level files into logical subdirectories using `git mv` (history preserved)
  - 16 ETL/import scripts → `etl/` (`import_*.py`, `init_*.py`, `rebuild_db.py`, `sync_stoc.py`, `update_data.py`, `merge_client_profi_mega.py`)
  - 13 OS/launcher files → `scripts/` (`start.sh`, `stop.sh`, `restart.sh`, `_torb_server.py`, `launcher.py`, all `.bat`/`.vbs`/`.ps1`)
  - Root now contains only config and documentation files
- Added directory structure rules and routing guide to `CLAUDE.md` (auto-loaded each session)

### Path fixes (required by reorganization)
- `etl/rebuild_db.py`, `etl/update_data.py`: added `sys.path.insert` for sibling dynamic imports
- `scripts/_torb_server.py`: `DIR` now resolves to project root (`dirname(dirname(__file__))`)
- `scripts/start.sh`, `scripts/stop.sh`: `DIR` derives from parent of scripts dir
- `scripts/torb_start.bat`, `torb_actualizeaza.bat`: added `ROOT` variable (parent of `scripts\`); log and script paths updated
- `scripts/ruleaza_import_preturi.bat`, `sync_stoc.bat`: `cd ..` to project root; ETL paths prefixed with `etl\`
- `scripts/setup_task_scheduler.ps1`: `$LogDir` now at project root
- `scripts/launcher.py`: `BASE_DIR` → `dirname(dirname(__file__))` when not frozen
- `app/app.py`: subprocess call updated from `update_data.py` → `etl/update_data.py`

### Testing
- Added `tests/conftest.py`: session-scoped temp SQLite DB with full schema and seed data; patches `DB_PATH` before app import
- Added `tests/test_bonus_calc.py`: 17 unit tests for `payout_multiplier`, `calc_month`, `simulate` (all grid thresholds, gates, penalties)
- Added `tests/test_etl_parsers.py`: 26 tests for ETL parsing functions (`normalize_ref`, `parse_order_date`, `num`, `s`, `extract_romanian_keyword`, `parse_filename_date`)
- Added `tests/test_flask_routes.py`: 9 smoke tests — all main routes return 200, API endpoints return valid JSON, 404 custom page, response shape assertions
- Total: 61 tests pass in CI

### CI/CD
- Test job: pinned to `tests/` directory, removed silent-pass fallback — failures now break the pipeline
- Added `smoke-test-vps` job after deploy: waits 15s, curls all main routes and API endpoints against live VPS, fails pipeline on any non-200
- Added code quality rules and auto-fix hook documentation to `CLAUDE.md` (ruff `--fix --quiet` runs on every `.py` write/edit)

## [0.1.0] - 2026-04-19

### Initial release

**Flask web application** (`app/`)
- Executive dashboard with revenue, agent, and brand KPIs
- Client explorer with drill-down detail pages
- Product/SKU browser
- Team performance view
- Bonus calculator page
- AI natural-language query interface (`/ask`) powered by Claude
- Agentic analytics endpoint (`/agent`)
- SQLite query layer (`queries.py`, 493 lines) with pre-built analytics queries
- Jinja2 templates for all pages with shared base layout and CSS

**Forecast module** (`forecast/`)
- Statistical demand forecasting engine using `statsforecast` (AutoETS/AutoARIMA)
- Brand-level and SKU-level forecast runs with configurable horizon
- Reorder suggestion engine (lead time, safety stock, service-level targets)
- Rolling-origin backtest (3 folds × 13 weeks; WAPE/MASE/bias/service-level metrics)
- Forecast export to Excel
- Brand hierarchy support
- Schema auto-creation on first run
- Flask UI pages: `/forecast` index, brand view, SKU view

**Data pipeline**
- `import_to_sqlite.py` — imports raw Excel transactions into `tranzactii` table (131,898 rows, 2024–2026)
- `import_stoc.py` — flexible stock snapshot importer (flexible column detection)
- `import_tables_extra.py` — imports additional reference tables
- SQLite views: `v_vanzari_an_furnizor`, `v_vanzari_luna_agent`, `v_vanzari_luna_client`, `v_top_sku`, `v_clienti`

**Project documentation**
- `CLAUDE.md` — project context and session instructions for Claude Code
- `STATUS.md` — execution status, delivered phases, open items
- `plan_strategic_5ani.md` — 5-year strategic plan (2026–2030), pillars, financial model
- `torb_background.md` — company background research
- `context/` — business overview, AI opportunities, key risks, data file reference, glossary, memory

**Infrastructure**
- `start.sh` / `stop.sh` / `restart.sh` — server lifecycle scripts with venv auto-detection
- `requirements.txt` — Python dependencies (Flask, pandas, numpy, scipy, statsforecast, openpyxl, anthropic)
- `.gitignore` — excludes venv, compiled Python, SQLite DB, and data files
