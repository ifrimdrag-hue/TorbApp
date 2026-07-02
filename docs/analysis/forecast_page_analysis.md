# Forecast page (`/forecast`) — deep-dive documentation & findings

*Analyzed 2026-07-02. Covers `app/templates/forecast.html`, `app/blueprints/forecast.py`,
`app/forecast/forecast_logic.py`, `app/queries/forecast.py`, `app/queries/orders.py`,
`app/forecast/forecast_agent.py`, plus live checks against `data/torb.db`.*

---

## 1. What the page is

"Stoc & Aprovizionare" — the procurement cockpit. One Flask route
(`forecast_bp.route('/forecast')`, [app/blueprints/forecast.py:50](../../app/blueprints/forecast.py#L50))
renders all five tabs in a single template; tab switching is a full page reload with
`?tab=` (all tab divs are rendered, non-active ones hidden with `display:none`).

| Tab | Purpose | Data source |
|-----|---------|-------------|
| **Stoc & Urgente** | Current stock per SKU + sales velocity + in-transit orders + editable RO/HU order suggestions | Server-rendered from `queries.forecast_stoc_extended()` |
| **Sugestie Comandă** | On-demand order suggestion per brand (multi-select), editable RO/Export split, save as draft/confirmed order | Client-side fetch `/api/forecast/suggest/<brand>` → `forecast_logic.build_suggestion()` |
| **Comenzi Furnizori** | Supplier order CRUD: lines, status lifecycle, Excel export/import | Server-rendered `queries.comenzi_list()` + lazy `/api/comenzi/<id>` |
| **Termene** | Per-brand lead times (`zile_livrare`), Christmas-season flag | `termene_aprovizionare` table |
| **Clienți Export** | Which clients count as "export" (HU) — drives the RO/HU demand split | `clienti_export` table |

Plus a floating **Agent Aprovizionare** chat (`/api/forecast/chat` →
`forecast/forecast_agent.py`, Claude with business-context system prompt).

### Template context

Route passes `rows, summary, brand_opts, gama_opts, lead_times, lt_map, comenzi, sel_*,
is_xmas_window, months_json, stoc_snapshot, today`. Three names come from app-level
Jinja globals/filters instead ([app/app.py:144-215](../../app/app.py#L144-L215)):
`sku_cod_mare` (context processor, SKU→cod_mare map), and filters `ron`, `days_until`.

---

## 2. Data model (SQLite, `data/torb.db`)

- **`stoc`** — stock snapshots, **one row per lot** (`UNIQUE(data_snapshot, cod_produs, data_intrare)`).
  All queries filter `data_snapshot = MAX(data_snapshot)` and `cantitate > 0`, then `GROUP BY sku`.
  Live check: latest snapshot has 699 rows / 343 distinct SKUs.
- **`tranzactii`** — sales lines. `cod_client` is TEXT (numeric strings like `'1429'`).
- **`clienti_export`** — export (HU) clients; `cod_client TEXT UNIQUE`. Active ones split demand into RO vs Export.
- **`termene_aprovizionare`** — per-brand lead time (`zile_livrare`), `sezon_craciun`, plus legacy
  columns (`zile_livrare_min`, `moneda`, `tip_produs`) used only by the older `/forecast/setari` page.
- **`comenzi_furnizori`** + **`comenzi_furnizori_linii`** — supplier orders. Header has both
  `data_estimata_livrare` and a later-added `eta` column (they diverge — see finding B6).
  Lines carry `cantitate_sugerat/comandata/confirmata`, RO/export split, price, and
  PFI-import columns (`units_per_carton`, `cantitate_baxuri`, kg, cbm).

DB access: `db.query()` reuses one read connection per Flask request (`g.db`);
`db.get_db()` returns a **fresh** connection for writes, caller commits/closes.
`PRAGMA foreign_keys` is only enabled in `migrations/runner.py`, **not** on app
connections — see finding C4.

---

## 3. The suggestion algorithm

Two implementations exist (see finding A-DUP):

### 3a. `forecast_logic.build_suggestion(furnizor, min_velocity, only_needed)` — Tab 2

1. **Lead time** from `termene_aprovizionare` (default 30 days).
2. **Monthly history** `_monthly_sales_by_sku(furnizor)`: last 3 years of `tranzactii`,
   grouped `(sku, luna, an)`, split into `ro` / `export` by `cod_client IN (active clienti_export)`,
   then **averaged per calendar month across years that had sales**. SKUs are normalized
   with `_normalize_sku()` (wraps a bare trailing EAN in parentheses so ERP-format and
   stoc-format SKUs match).
3. **Coverage demand** `_coverage_demand(monthly_avg, lead_days)`: expected demand from
   today through `today + lead_days + SAFETY_DAYS(30)`, walking month by month at each
   month's daily rate (seasonality-aware).
4. **Availability** = current stock (latest snapshot) + in-transit
   (`get_in_transit`: sum of `COALESCE(cantitate_confirmata, cantitate_comandata)` over
   orders with status in emisa/confirmata/in_tranzit, both capitalizations).
5. **RO-first split**: stock+transit covers RO demand first; leftover covers export:
   ```
   suggested_ro     = max(0, demand_ro − available)
   surplus          = max(0, available − demand_ro)
   suggested_export = max(0, demand_export − surplus)
   ```
6. **Urgency** (Tab 2): `zile_stoc = (stock+transit)/(avg_monthly/30)`;
   `critic` if `< lead_days`, `atentie` if `< lead_days + 30`, else `ok`.
7. **Christmas**: `is_xmas` per SKU if brand has `sezon_craciun` and Oct/Nov seasonality
   index > 1.3. Page-level banner `is_xmas_window()` = hardcoded **April–May**
   (order window for 4-month-lead brands; matches the agent prompt).
8. `min_velocity` drops slow movers; `only_needed` keeps `suggested > 0`; sort critic→ok, then by qty.

Multi-brand selection in the UI fires one fetch per brand in parallel and merges
client-side (`loadSuggestion()` in the template).

### 3b. `queries.forecast_stoc_extended()` — Tab 1

Re-implements the same split inline: SQL for stock + 90-day velocity + RO/HU 90-day split,
then Python loop that pulls the same `_monthly_sales_by_sku` / `_coverage_demand` per brand
to compute `suggested_ro` / `suggested_hu` and **overwrites** `vanzari_luna_avg` and
`zile_stoc` with 3-year-average versions. Also appends synthetic rows for:
- SKUs with active transit but no physical stock;
- SKUs sold in the last 90 days but absent from the snapshot (with `zile_stoc = 0` → shown Critic).

### Order lifecycle

`draft → confirmata → in_tranzit → livrata` (or `anulata`) via the status modal
(`/api/comenzi/<id>/status`), which also records per-line supplier-confirmed quantities.
Once in emisa/confirmata/in_tranzit, an order's lines count as in-transit stock in both
suggestion paths. A separate `/api/comenzi/<id>/avanseaza` endpoint implements an older
capitalized flow (`Emisa → Confirmata → In tranzit → Receptionata`) — it is dead and broken
(finding A2). ETL scripts `etl/import_comenzi_tranzit_*.py` insert orders with the
**capitalized** statuses; the live DB currently contains only capitalized statuses.

---

## 4. Tab 1 "Stoc & Urgente" — column-by-column reference

Everything comes from `queries.forecast_stoc_extended()`
([app/queries/forecast.py:219](../../app/queries/forecast.py#L219)) plus a bit of
template math in [forecast.html:187-298](../../app/templates/forecast.html#L187-L298).

### Row sources

The table is a union of three row kinds:

1. **Stock rows** — latest snapshot (`data_snapshot = MAX(...)`), `cantitate > 0`,
   one row per SKU (`GROUP BY s.sku, s.furnizor, s.gama` over the per-lot rows).
2. **Transit-only rows** — SKUs on an active order (emisa/confirmata/in_tranzit) with no
   physical stock. Synthetic: `stoc_total = 0`, `gama = NULL`.
3. **Sold-but-absent rows** — SKUs with sales in the last 90 days that are missing from
   the snapshot entirely. Synthetic: `stoc_total = 0`, **`zile_stoc = 0`** → always shown
   Critic (deliberate: it's sold and out of stock).

Filters: *Brand* → `s.furnizor =`, *Gamă* → `s.gama =`, *Caută* →
`LIKE %q%` on `cod_produs` / `cod_mare` / `sku`; *Urgență* is applied last, in Python,
on the final `zile_stoc` value (<30 critic, 30–59 atenție, else/NULL ok).

### Columns

| Column | How the value is computed |
|---|---|
| **Cod furnizor** | `sku_cod_mare.get(r.sku) or r.cod_produs`. `sku_cod_mare` is an app-wide Jinja global ([_shared.py:26](../../app/queries/_shared.py#L26)): `{sku → cod_mare}` from **any** stock snapshot, with `cod_furnizor` from order lines as fallback. `r.cod_produs` is `MAX(s.cod_mare)` in the latest snapshot; for transit-only rows it's the order line's `cod_furnizor`; for sold-but-absent rows it's historical `cod_mare` or, failing that, derived by regex from the SKU (`…71725` → `71725-00`). |
| **SKU** | `stoc.sku` verbatim (or `tranzactii.sku` / order-line SKU for synthetic rows). Links to `/produs/<sku>`. |
| **Brand** | Badge shows `r.gama or r.furnizor` — the *gama* wins when present, despite the column header; synthetic rows always show the furnizor (gama is NULL). |
| **Stoc (buc)** | `SUM(s.cantitate)` across the SKU's lots in the latest snapshot. `0` for synthetic rows. |
| **Val. stoc** | `ROUND(SUM(s.cantitate × s.pret_achizitie), 2)`, displayed with the `ron` filter. Acquisition value, not sale value. |
| **În tranzit (per comandă)** | One chip per `(sku, nr_comanda)`: qty = `SUM(COALESCE(cantitate_confirmata, cantitate_comandata))` over lines of orders with status emisa/confirmata/in_tranzit (both capitalizations). ETA shown = `data_estimata_livrare` only — the newer `eta` column is ignored (finding B6). Chip color, computed in the template with the `days_until` filter: gray = no ETA; green = arrives before projected stock-out (`days_to_eta ≤ zile_stoc`); yellow = within 30 days after stock-out; red = later than that; blue = ETA known but `zile_stoc` unknown. |
| **Stoc + tranzit** | Template math: `stoc_total + in_tranzit_qty`. Rendered only when transit > 0, otherwise "—". |
| **Vânz./lună** | The SQL first computes a 90-day velocity (`SUM(cantitate) last 90d / 3`), but Python then **unconditionally overwrites** it with the 3-year figure: for each calendar month, average the month's qty across the years that had sales, then `sum(12 month-averages) / 12` (this is the source of the B4 bias — zero months aren't zero-filled). "—" when 0. |
| **Zile stoc** | SQL baseline: `stoc / (velocity_90d / 30)`. Overwritten in Python whenever the 3-year average > 0 with `int((stoc + tranzit) / (avg_3yr / 30))` — i.e. it silently **includes transit** (finding B2). `NULL` (shown "—") when the SKU has no sales history; `0` for sold-but-absent rows. |
| **Zile cu tranzit** | Computed in the template: `round((stoc_total + tranzit) / (vanzari_luna_avg / 30))`. Because of the B2 overwrite this is the *same formula* as Zile stoc, so both columns show the same number whenever transit > 0. Rendered only when transit > 0. |
| **Urgență** | Badge + row color from `zile_stoc`: `< 30` → Critic (red row), `< 60` → Atenție (yellow), else or NULL → OK. Fixed thresholds, not lead-time-aware — unlike Tab 2 (finding B7). |
| **Cel mai vechi lot** | `MIN(s.data_intrare)` across the SKU's lots in the latest snapshot. NULL for synthetic rows. |
| **Clienți** | Button only — opens the modal via `GET /api/forecast/sku-clients/<sku>` (`sku_clients_monthly`: per client, per year, 12 monthly quantities from `tranzactii`, sorted by total). |
| **Sug. RO** (editable) | `max(0, round(demand_ro − available))` where `demand_ro = _coverage_demand(monthly_ro, lead)` — expected RO demand from today through `today + zile_livrare + 30` walking month-by-month at each month's daily rate — and `available = stoc + tranzit`. `monthly_ro` = 3-year monthly averages of sales to clients **not** in active `clienti_export`. `lead` = brand's `zile_livrare` (default 30 if the brand has no Termene row). Tooltip shows `avg_monthly_ro` (= `sum(RO month-averages)/12`) and the lead time. |
| **Sug. HU** (editable) | `max(0, round(demand_hu − surplus))` where `demand_hu` is the same coverage demand computed from export-client sales and `surplus = max(0, available − demand_ro)` — stock covers RO first, only the leftover offsets the export order. ⚠ Currently always 0 because no transactions match the configured export codes (finding A1). |
| **+ Comandă** | Button opens the "add to draft order" modal; quantities prefill from whatever is currently typed in the row's Sug. RO / Sug. HU inputs (matched by row index). The `data-pret`/`data-moneda` attributes are always empty because the query doesn't select those columns (finding A5). |

### 4.1 Deep dive: Vânz./lună — files, exact code, and whether the SQL value survives

**Files & code involved, in execution order:**

| Step | File : lines | What happens |
|---|---|---|
| 1. Display | [app/templates/forecast.html:242](../../app/templates/forecast.html#L242) | `{{ r.vanzari_luna_avg }}` ("—" when 0). Also reused at [line 198](../../app/templates/forecast.html#L198) to compute the *Zile cu tranzit* cell. |
| 2. Route | [app/blueprints/forecast.py:59](../../app/blueprints/forecast.py#L59) | `queries.forecast_stoc_extended(...)` produces `rows`. |
| 3. SQL (value **A**, 90-day) | [app/queries/forecast.py:246-250](../../app/queries/forecast.py#L246-L250) | Subquery `v`: `SUM(cantitate)/3.0` over `tranzactii` with `data_dl >= date('now','-90 days')`, grouped by SKU — **no furnizor filter**. Selected at [line 238](../../app/queries/forecast.py#L238) as `vanzari_luna_avg`. |
| 4. SQL uses of A | [app/queries/forecast.py:239-241](../../app/queries/forecast.py#L239-L241), [263](../../app/queries/forecast.py#L263) | A feeds the SQL `zile_stoc` (`stoc/(A/30)`) and `ORDER BY zile_stoc ASC` — the row order of the whole table. |
| 5. History (value **B**, 3-year) | [app/queries/forecast.py:296-300](../../app/queries/forecast.py#L296-L300) → [app/forecast/forecast_logic.py:86-137](../../app/forecast/forecast_logic.py#L86-L137) | `_monthly_sales_by_sku(furnizor)` per brand present in the rows: `tranzactii` with `an >= today.year − 3` **and `furnizor = :f`**, split RO/export via `get_export_codes()` ([forecast_logic.py:20-31](../../app/forecast/forecast_logic.py#L20-L31)), keyed by `_normalize_sku()` ([forecast_logic.py:34-46](../../app/forecast/forecast_logic.py#L34-L46)). Per calendar month: average across years **that had sales**; `B = sum(12 month-averages)/12`. |
| 6. Overwrite | [app/queries/forecast.py:329-334](../../app/queries/forecast.py#L329-L334) | `r['vanzari_luna_avg'] = round(B, 1)` — **unconditional**; `r['zile_stoc']` overwritten too, but **only when B > 0** (and then it includes transit). |
| 7. Synthetic rows | [app/queries/forecast.py:363/380](../../app/queries/forecast.py#L363-L380), [422/438](../../app/queries/forecast.py#L422-L438) | Transit-only and sold-but-absent rows get `vanzari_luna_avg = B` directly (no SQL value exists for them). |

**So is the SQL (90-day) value A obsolete?** Not entirely — it leaks out in three ways:

1. **Row order.** The table is sorted by the SQL `zile_stoc` (derived from A, physical stock
   only). Python overwrites the displayed values but never re-sorts, so the table is *not*
   actually ordered by the "Zile stoc" numbers you see.
2. **`zile_stoc` fallback.** When B = 0 but A > 0 — possible because A ignores `furnizor`
   while B requires `tranzactii.furnizor` to equal the stock row's brand (brand-label
   mismatches, e.g. re-branded SKUs) — the overwrite at step 6 is skipped and the
   displayed *Zile stoc* is still the 90-day/A-based SQL value, while *Vânz./lună* shows
   "—" (B=0). A row showing days-of-stock with no velocity is this case.
3. **The Excel export shows A, not B.** The tab's *Export* button
   ([forecast.html:157](../../app/templates/forecast.html#L157)) calls
   `reports.export_excel?report=forecast` →
   [app/blueprints/reports.py:235-243](../../app/blueprints/reports.py#L235-L243) → which
   uses **`forecast_stoc_brand`** ([app/queries/forecast.py:139-216](../../app/queries/forecast.py#L139-L216)),
   not `forecast_stoc_extended`. That function returns the raw SQL values with **no Python
   overwrite** — so the exported `vanzari_luna_avg` / `zile_stoc` are the 90-day figures
   and can differ substantially from what the page shows. The export also silently drops
   the `q` search filter (the template passes it; reports.py never reads it) and contains
   none of the synthetic rows or RO/HU columns.

Related dead code: `forecast_stoc()` ([app/queries/forecast.py:5](../../app/queries/forecast.py#L5))
has no callers anywhere — only re-exported in `queries/__init__.py`.

**Recommendation:** pick one velocity definition. Either (a) make the export use
`forecast_stoc_extended` so page and Excel agree, and drop `forecast_stoc`/`forecast_stoc_brand`;
or (b) if the 90-day velocity is the *intended* "recent" signal, show both columns
explicitly (recent 90d vs 3-year seasonal) instead of overwriting one with the other.
Also re-sort `rows` in Python after the overwrite so the visible order matches the
displayed days-of-stock.

### KPI cards above the table

`queries.forecast_summary()` — computed independently of the table rows, per stock **lot**
(not per SKU) and with the 90-day velocity (not the 3-year average), so the cards do not
reconcile with the table badges or with "SKU-uri în stoc" (finding B1). "Valoare stoc" =
`SUM(cantitate × pret_achizitie)` over the latest snapshot.

---

## 5. API surface (all in `blueprints/forecast.py`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/forecast/suggest/<furnizor>` | GET | Build suggestion (params `min_velocity`, `only_needed`) |
| `/api/forecast/sku-clients/<sku>` | GET | Per-client monthly sales history (modal) |
| `/api/comenzi` | POST | Create order + lines (`status` optional) |
| `/api/comenzi/drafts` | GET | Draft orders for "add to order" dropdown |
| `/api/comenzi/<cid>` | GET/PUT/DELETE | Order header + lines |
| `/api/comenzi/<cid>/lines` | POST | Upsert line (by `comanda_id+sku`) |
| `/api/comenzi/<cid>/lines/<lid>` | PUT/DELETE | Update/delete line |
| `/api/comenzi/<cid>/status` | POST | Status + dates + per-line confirmed qty |
| `/api/comenzi/<cid>/avanseaza` | POST | **Dead/broken** legacy status advance |
| `/api/termene-aprovizionare` | POST | Upsert lead time (Termene tab) |
| `/api/clienti-export` | GET/POST | Export clients list/upsert |
| `/api/clienti-export/<cod>` | DELETE | Remove export client |
| `/api/clienti/search` | GET | Client autocomplete from `tranzactii` |
| `/export/forecast/comanda/<cid>` | GET | Excel in Basilur PFI layout |
| `/import/forecast/comanda/<cid>` | POST | Import lines from Excel (needs SKU + "COMAND*" columns) |
| `/api/forecast/refresh-stoc` | POST | Re-run `etl/import_stoc.py` (sync, 120 s) |
| `/api/actualizare-date` (+`/status`) | POST/GET | Run `etl/update_data.py` in a daemon thread |
| `/api/upload/<tip>` (+`/status/<job>`) | POST/GET | Async file upload → matching ETL script |
| `/api/forecast/chat` | POST | AI procurement agent |

---

## 6. Findings — bugs and inconsistencies

Ordered by severity. **A = broken now, B = wrong results/logic, C = latent/robustness, D = cleanup.**

### A1. Export (HU) split is completely dead with current data — CRITICAL
`clienti_export.cod_client` holds `'BRANDMIX'` / `'HUNTRADE'`, but `tranzactii.cod_client`
for those clients is `'1429'` / `'1430'` (names "BRANDMIX KFT", "HUN-TRADE KFT").
`SELECT COUNT(*) FROM tranzactii WHERE cod_client IN ('BRANDMIX','HUNTRADE')` → **0**.
Consequence: every `avg_monthly_export`, `suggested_export`, "Sug. HU", "Avg/lun Exp"
on both tabs is 0; all demand is treated as RO. The feature silently no-ops.
**Fix:** `UPDATE clienti_export SET cod_client='1429' WHERE cod_client='BRANDMIX';`
(same for `'1430'`/`'HUNTRADE'`), and add a validation on insert: reject codes that
don't exist in `tranzactii.cod_client` (the UI autocomplete already supplies real codes;
these two rows likely predate it).

### A2. Status-vocabulary split can silently corrupt orders — CRITICAL
The DB currently holds only **capitalized** legacy statuses (`Emisa`, `Confirmata`,
`In tranzit` — 8 orders, inserted by the tranzit-import ETLs). The UI works exclusively
in lowercase (`draft/confirmata/in_tranzit/livrata/anulata`). Consequences:
1. **Data corruption path:** `openStatusModal(cid, 'In tranzit', …)` sets a `<select>`
   whose options are lowercase → no option matches → `select.value === ''` → `saveStatus()`
   posts `status: ''` → `comanda_update` only filters `None`, so it writes `status=''`.
   The order then vanishes from every in-transit calculation → suggestions inflate.
2. The Comenzi tab status filter (lowercase values) never matches legacy rows.
3. Badge colors default to gray for legacy statuses (`status_class` map is lowercase-only).
4. The AI agent's in-transit context query ([forecast_agent.py:67](../../app/forecast/forecast_agent.py#L67))
   checks **only lowercase** → the agent currently sees zero in-transit orders.
`forecast_logic.get_in_transit` and `forecast_stoc_extended` defensively match both
spellings, which hides the problem in the numbers while the UI misbehaves.
**Fix:** one-time migration normalizing statuses to lowercase (`Emisa→confirmata` or a new
`emisa`, `In tranzit→in_tranzit`, `Receptionata→livrata`), update the tranzit-import ETLs
to write lowercase, then delete the dual-case `IN (...)` lists. Also make
`comanda_update` reject/skip empty-string status.

### A3. `/api/comenzi/<id>/avanseaza` crashes — dead code
[blueprints/forecast.py:722](../../app/blueprints/forecast.py#L722) calls
`queries.query_one`, which the `queries` package does not re-export → `AttributeError`
→ 500 on every call. Nothing in the templates references it, and its flow
(`Emisa→…→Receptionata`) conflicts with the real lifecycle. **Fix: delete the endpoint.**

### A4. Export-clients tab actions broken for the existing rows
`loadExportClients()` renders `onchange="toggleExportClient(${c.cod_client}, …)"` and
`onclick="deleteExportClient(${c.cod_client})"` — unquoted. For numeric codes this works;
for the current text codes it emits `toggleExportClient(BRANDMIX, …)` → `ReferenceError`,
so the Activ toggle and delete button do nothing for exactly the two rows that exist.
`addExportClient()` also does `parseInt(cod)` and refuses non-numeric codes.
**Fix:** quote the code (`'${c.cod_client}'` with proper escaping) and drop the `parseInt`
(codes are TEXT in the schema). Fixing A1 (numeric codes) also masks this, but the JS
is still wrong for any future non-numeric code.

### A5. Tab 1 "add to order" never carries a price
The row buttons pass `data-pret="{{ r.pret_valuta }}"` / `data-moneda="{{ r.moneda_valuta }}"`
([forecast.html:283-284](../../app/templates/forecast.html#L283-L284)), but
`forecast_stoc_extended()` does **not** select those columns (only the unused
`forecast_stoc_brand()` joins `costuri_landing`). Jinja renders empty strings, so every
line created from Tab 1 has `pret_valuta = NULL`. **Fix:** add the `costuri_landing`
join (as in `forecast_stoc_brand`) to `forecast_stoc_extended`.

### B1. KPI cards count lots, not SKUs, and use a different velocity than the table
`forecast_summary()` ([queries/forecast.py:55](../../app/queries/forecast.py#L55)) computes
Critic/Atenție/OK with `SUM(CASE …)` over raw `stoc` rows — one per **lot** (699 rows vs
343 SKUs in the live snapshot), so the three cards sum to ~699 while "SKU-uri în stoc"
says 343, and a multi-lot SKU counts multiple times. Additionally the cards use 90-day
velocity while the table rows below recompute `zile_stoc` with the 3-year monthly average
(and *including transit*, see B2) — so card counts don't match the badges in the table.
**Fix:** aggregate to SKU level first (`COUNT(DISTINCT CASE WHEN … THEN sku END)` over the
per-SKU subquery), and ideally compute the summary in Python from the same `rows` the
table uses so one definition exists.

### B2. Tab 1 "Zile stoc" secretly includes transit → duplicate column
[queries/forecast.py:333-334](../../app/queries/forecast.py#L333-L334) overwrites
`zile_stoc = (stoc + tranzit) / avg`. The template then computes "Zile cu tranzit" with the
same formula, so whenever transit > 0 the two columns show the **same number** and the
"Zile stoc" column under-reports urgency of physical stock. The transit-chip coloring
(`days_to_eta <= zile`) also compares against the transit-inclusive figure.
**Fix:** keep `zile_stoc` = physical stock only; let the template's `zile_total` be the
with-transit view (as its header promises).

### B3. "Confirmă Comanda" orders hidden rows too
In Tab 2, `updateTotal()` skips rows hidden by the search/export filter, but `saveOrder()`
iterates **all** rows — and every input is prefilled with the suggested qty. Filter to 5
SKUs, check the footer total, hit save → the created order contains *all* SKUs, at a much
larger total than displayed. **Fix:** either skip `display:none` rows in `saveOrder()`
(and say so in the UI), or make the footer count all rows; the two must agree.

### B4. Demand overstated for delisted/declining SKUs
`_monthly_sales_by_sku` averages each calendar month **only across years that had sales**
(months with zero sales produce no `tranzactii` rows, so nothing is appended). A SKU that
sold 100/mo in 2024 and nothing since still shows avg 100 → suggestions keep reordering
dead items (velocity `min_velocity` filter uses the same inflated average). Conversely
`avg = sum(months)/12` under-weights SKUs launched mid-history — acceptable annualization,
but combined the bias is asymmetric. **Fix:** zero-fill months between the SKU's first
sale and today before averaging, or weight recent 12 months higher.

### B5. In-transit counts forever, even overdue
Both suggestion paths subtract full in-transit quantity regardless of ETA. Live DB: orders
#6/#7 have ETA **2026-05-29** (five weeks past) and still count as incoming, suppressing
suggestions. Nothing flags an order whose ETA passed. **Fix:** surface "overdue transit"
(ETA < today) in the UI and/or exclude orders overdue by more than X days from
`available`.

### B6. Tab 1 transit chips read the stale ETA column
`comenzi_furnizori` has both `eta` and `data_estimata_livrare`; they diverge (order #1:
`eta=2026-07-21` vs `data_estimata_livrare=2026-06-02`). `forecast_stoc_extended` selects
only `data_estimata_livrare AS eta`, while the unused `forecast_stoc_brand` correctly does
`r['eta'] or r['data_estimata_livrare']`. Tab 1 therefore shows outdated (already-past)
delivery dates. **Fix:** `COALESCE(c.eta, c.data_estimata_livrare)` in the extended query —
or better, drop one of the two columns (tech-debt: two fields, same meaning).

### B7. Urgency means different things per tab
Tab 1: fixed 30/60-day thresholds. Tab 2: lead-time-based (`< lead_days` = critic). A
Basilur SKU (120-day lead) with 100 days of stock is **Critic** in Tab 2 but **OK** in
Tab 1. Defensible, but nothing on the page explains it. **Fix:** use lead-time-based
thresholds in both (fixed 30/60 is meaningless for a 120-day-lead brand), or label the
badges differently.

### B8. Round-trip Excel export → import always fails
`export_comanda` writes headers `CODE, PRODUCT DESCRIPTION, No of Units, …, — SKU intern,
— Cantitate sugerat…`; `import_comanda_lines` requires a header containing `SKU` (found:
"— SKU INTERN") **and** one containing `COMAND` (found: none) → "Nu am găsit coloanele".
So the natural workflow "export, edit quantities, re-import" is impossible.
**Fix:** accept `No of Units` (or add a `— Cantitate comandată` column to the export).

### C1. Status-modal `onclick` breaks on special characters (stored XSS vector)
`onclick="openStatusModal({{ c.id }}, '{{ c.status }}', …, `{{ c.observatii or '' }}`)"`
puts user text inside a JS template literal. Jinja autoescape does not escape backticks or
`${`, so an observation containing `` ` `` breaks the handler, and `${…}` executes JS.
Internal tool → low severity, but trivial to hit accidentally. **Fix:** pass data via
`data-*` attributes (as the SKU buttons already do) and read `dataset` in JS. Same pattern
issue in `sendAgentMsg()` (user question and AI answer inserted as raw HTML) and
`loadExportClients()` (only single quotes escaped).

### C2. `comanda_update` can't clear fields, accepts empty strings
Filtering `v is not None` means a date/observation can never be cleared from the modal
(sending `null` is ignored), while `''` **is** written (this enables A2's `status=''`).
**Fix:** treat `''` as `NULL` for dates/status, and allow explicit clearing.

### C3. SQL built by string interpolation in `_monthly_sales_by_sku`
Export codes are quoted into the SQL text (`f"'{c}'"`). Codes come from the admin-editable
`clienti_export` table; a code containing `'` breaks the query. **Fix:** bind parameters
(`IN (:c0,:c1,…)`) or a subselect `cod_client IN (SELECT cod_client FROM clienti_export
WHERE activ=1)` like `forecast_stoc_extended` already uses.

### C4. `ON DELETE CASCADE` is inert — `foreign_keys` pragma never enabled in the app
Only `migrations/runner.py` sets `PRAGMA foreign_keys=ON`; `db.py` connections don't.
`comanda_delete` deletes only the header, relying on the cascade → orphan lines. Live DB
has 0 orphans today, but any header delete leaves garbage that only stays invisible
because every reader JOINs to the header. **Fix:** add `PRAGMA foreign_keys=ON` to
`_PER_CONN_PRAGMAS`, or delete lines explicitly in `comanda_delete`.

### C5. `_listing_changes` keys are un-normalized SKUs
Returns raw `tranzactii.sku` keys, but callers look up with `_normalize_sku(sku)` — the
+N/−N listing badge silently misses SKUs whose ERP spelling differs (bare EAN). **Fix:**
normalize keys in `_listing_changes` too.

### D1. Dead code in the template and blueprint
- `actualizareDate()` / `refreshStoc()` (forecast.html:978, 1001) — no button calls them
  on this page (`refreshStoc` also relies on the deprecated implicit global `event`).
- The `DOMContentLoaded` tab-click handler (forecast.html:901-908) computes `tabId` and
  does nothing.
- `merged.lead_time` is taken from the first selected brand while the info box shows the
  max — harmless but confusing.
- `/forecast/setari` + `termene_aprovizionare_upsert` (zile_min/zile_max/moneda/tip_produs)
  is a parallel, older settings page for the same table as the Termene tab.

### D2. Mojibake in user-facing strings in `blueprints/forecast.py`
The file contains double-encoded UTF-8 (verified bytes `\xc3\x84\xc6\x92` = broken "ă"),
e.g. the 404 message renders as "ComandÄƒ negÄƒsitÄƒ" in UI alerts. This is the known
encoding debt documented in `docs/TECHNICAL.md` §Encoding — fix with the
repair script there, not with the Edit tool.

### D-DUP. Two parallel implementations of the same algorithm
`forecast_logic.build_suggestion` (Tab 2) and `queries.forecast_stoc_extended` (Tab 1)
duplicate the demand/split/urgency logic and have already diverged (price columns — A5,
ETA source — B6, urgency — B7, transit qty COALESCE differences vs `forecast_stoc_brand`).
Longer term, extract one shared per-SKU computation in `forecast_logic` and have both
callers consume it. `forecast_stoc` / `forecast_stoc_brand` appear superseded by
`forecast_stoc_extended` — candidates for deletion after confirming no other callers.

---

## 7. Suggested fix order

1. **A1** (export codes) + **A4** (quote codes in JS) — restores the RO/HU feature; data-only fix is one UPDATE.
2. **A2** (status normalization migration + guard against `status=''`) — prevents order corruption.
3. **A3** delete dead endpoint; **A5** price join; **B6** ETA coalesce — small, mechanical.
4. **B1/B2** (summary per-SKU, zile_stoc without transit) — makes the numbers self-consistent.
5. **B3** (saveOrder vs filter) — prevents accidental over-ordering.
6. **B4/B5/B7** — algorithm-quality improvements; validate with the owner (ties into the open Basilur forecast validation).
7. **C/D** items opportunistically.
