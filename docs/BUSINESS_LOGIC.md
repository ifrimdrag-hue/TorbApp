# Business Logic — Implemented Functionality

Documentation of the domain model and the logic behind delivered features. Consolidated 2026-07-02 from `context/glossary.md` (data-model sections) and `.claude/project_knowledge.md` (Shopify sync, virtual brands). Business/company context is in `docs/BUSINESS.md`; infrastructure and data-layer mechanics in `docs/TECHNICAL.md`.

---

## 1. Domain vocabulary — key concepts

| Term | Plain meaning | ⚠️ Gotcha |
|---|---|---|
| **Furnizor** | Brand (Basilur, Toras…) | NOT the Sri Lanka vendor |
| **Agent** | Sales rep or channel | Includes EMAG, SITE (not human) |
| **Client** | Torb's customer (retailer) | NOT the end consumer |
| **Baza** | Raw transaction data | Excel sheet name; = `tranzactii` in DB |
| **Gama** | Product line within a brand | Derived at import time (`derive_gama()` / `GAMA_MAP`) |
| **IKA** | Large retail chains | = Key Accounts = Modern Trade |
| **TT** | Traditional trade | Small shops, visited by field agents |
| **Val Neta** | Net revenue | Primary revenue figure |
| **Marja Bruta** | Gross margin RON | val_neta − val_achizitie |
| **Scor** | Bonus performance score | Weighted avg of KPI achievements |
| **Cantitativ** | Unit-quantity target | vs. value target (RON) |
| **Phasing** | Monthly split of annual target | Oct–Dec = peak (gifting season) |
| **YTD** | Year to date cumulative | |
| **DL** | Delivery note | Groups all SKU lines in one shipment |

---

## 2. Data model (SQLite — torb.db)

```
  ┌──────────────────────────────────────────────────────────────┐
  │                        tranzactii                            │
  │  (131,898 rows — one row per SKU line per delivery note)     │
  │                                                              │
  │  TIME         luna, an, data_dl                             │
  │  DOCUMENT     nr_dl, nr_factura, nr_comanda                 │
  │  PRODUCT      cod_produs, sku, furnizor (=brand), um        │
  │  QUANTITY     cantitate                                      │
  │  FINANCIALS   val_neta, val_bruta, val_achizitie,           │
  │               marja_bruta, val_usd, discount_pct            │
  │  CLIENT       client, cod_client, tip_client,               │
  │               oras_client, judet_client                     │
  │  AGENT        agent  (sales rep OR channel)                 │
  └──────────────┬───────────────────┬──────────────────────────┘
                 │                   │
       agent ◄───┘                   └───► client
         │                                   │
         ▼                                   ▼
  ┌─────────────┐                   (no separate table yet —
  │   echipa    │                    client data is embedded
  │  (5 rows)   │                    in tranzactii)
  │             │
  │ employee_id │
  │ rol         │◄────────────────────────────────────┐
  │ activ       │                                     │
  │ bonus_target│                                     │
  └──────┬──────┘                                     │
         │                                            │
         ▼                                            │
  ┌─────────────────────┐    ┌─────────────────────┐  │
  │   targeturi_kpi     │    │    actuale_kpi       │  │
  │   (60 rows)         │    │    (60 rows)         │  │
  │                     │    │                     │  │
  │ an, luna,           │    │ an, luna,           │  │
  │ employee_id ────────┼────┼─► employee_id ──────┘  │
  │ net_sales (target)  │    │ net_sales (actual)      │
  │ gross_margin        │    │ gross_margin            │
  │ active_clients      │    │ active_clients          │
  │ collections         │    │ collections             │
  │ ...                 │    │ penalizare_erori_pct    │
  └─────────────────────┘    └─────────────────────────┘

  ┌──────────────────────────────────────────┐
  │         targeturi_cantitativ             │
  │         (20,919 rows)                    │
  │                                          │
  │  agent   ──────────────────► sales rep   │
  │  client  ──────────────────► buyer       │
  │  sku     ──────────────────► product     │
  │  an, luna                                │
  │  cantitate  (units planned/sold)         │
  │                                          │
  │  2024: historical actuals                │
  │  2025: historical actuals                │
  │  2026: targets (⚠ mostly zero, not set)  │
  └──────────────────────────────────────────┘
```

Rebuild commands, views, and migration mechanics: `docs/TECHNICAL.md` §Data.

---

## 3. Transaction anatomy

What a single row in `tranzactii` represents:

```
  One delivery (nr_dl) can have many invoice lines:

  DL: 301225024  (delivery note, date: 2025-12-31)
  Factura: TORB25121178
  Agent: EMAG
  Client: 3NYBLE TECHNOLOGIES SRL
  │
  ├── Line 1:  cod_produs=1561
  │            sku="B.CEAI FRUIT INFUSIONS ASSORTED 40E 72G"
  │            furnizor=Basilur
  │            cantitate=3, pret_vanzare=29.35
  │            val_neta=88.05, val_achizitie=31.46
  │            marja_bruta=56.59  (64% margin)
  │
  └── Line 2:  cod_produs=1236
               sku="B.CEAI STRAWBERRY & RASPBERRY 25X1.8G"
               furnizor=Basilur
               cantitate=1, pret_vanzare=20.18
               val_neta=20.18, val_achizitie=2.18
               marja_bruta=18.00  (89% margin)
```

---

### The Auchan/Tobra exception

Torb→Auchan sales are invoiced through the intermediary **Tobra Invest SRL**
(cod_client 719 in Torb's ERP). Shared constants: `app/business_constants.py`.

- `etl/import_vanzari_erp.py` diverts Torb→Tobra invoice lines (cod 719) out of
  `tranzactii` into the cost table `corr_vanzari_tobra` — Torb's true acquisition
  cost per product over time.
- `etl/import_vanzari_tobra_auchan.py` imports Tobra→Auchan invoices as if they
  were Torb→Auchan sales (client 732 `AUCHAN ROMANIA SA`, agent Oana Filip;
  invoice numbers keep the `TOBRA` prefix as a marker).
- **Cost rule (2026-07-02):** each imported row's `pret_cumparare` is overridden
  with the simple average of `corr_vanzari_tobra` costs for that `cod_produs` over
  the 30 days before the row's own `data_dl`; fallback: most recent cost ≤ row
  date, then the value from the Tobra file. `val_achizitie` and `marja_bruta`
  are recomputed. Upload order matters: import Vânzări ERP before Vânzări
  Auchan so the cost table is fresh.

---

## 4. Bonus calculation

### Current implementation (delivered 2026-06-16, migration 0011)

Config-driven bonus module: monthly objectives per agent (vânzări, marjă, 9 game individuale, nr. clienți, clienți noi/gamă, încasări, scriptic), configurable weights + bonus value, payout grid with thresholds (gate 80%), default objective = +20% growth vs same month last year, month-close flow with frozen snapshot, agent management from the UI.

- Tables: `bonus_config`, `bonus_lunar_config`, `bonus_obiective_strategice`, `bonus_payout_grid`, `bonus_istoric`
- Pages: `/bonus`, `/bonus/obiective`, `/bonus/inchidere`, `/bonus/config`, `/bonus/clienti-noi-gama`
- Full design + implementation plan: `docs/plans/2026-06-16-modul-bonus-redesign.md`

### Original Excel-based design (reference — the system the module replaced)

```
  Each month, per employee:

  tranzactii  ──────────────────────────────────────────────►  actuale_kpi
  (actual sales)     compute:                                  (filled in)
                     - Net Sales (val_neta sum)
                     - Gross Margin (marja_bruta sum)
                     - Active Clients (COUNT DISTINCT client)
                     - Collections (manual input)
                     - Promo Exec (manual input)
                     - Forecast (manual input)

  targeturi_kpi ───────────────────────────────────────────►  scor per KPI
  (monthly targets)  formula:                                  = actual / target
                     each KPI weighted by rol (02_Rol_KPI)

                     Scor final = Σ (KPI_score × KPI_weight)

  Scor final  ─────────────────────────────────────────────►  payout
                     prag minim = 0.85  → below = 0 bonus
                     scor 1.0   → payout 1.0  (100% of target bonus)
                     scor 1.2   → payout 1.4  (140% — max)
                     + penalizari (manual deductions)

  payout × bonus_target_lunar_ron  ────────────────────────►  bonus lunar (RON)
  (from echipa)
```

---

## 5. Virtual brands (KingsLeaf, Tipson, Organsia)

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

## 6. Stock synchronisation (eMAG + Shopify)

Unified UI at `/stocuri` (served by `stocuri_emag.py`) — radio btn-group switches platforms, driven by a `PLATFORMS` config object in `app/static/js/stocuri.js`; old `/stocuri/emag` and `/stocuri/shopify` redirect there. Both platforms follow the same flow: upload the internal stock report Excel → `preview()` diff → user review → `sync()`.

- **eMAG**: sync via eMAG Marketplace API v4.5.1 (HTTP Basic Auth). Request log: `logs/emag_req.json`.
- **Shopify**: sync via Shopify GraphQL Admin API (2025-04), OAuth client credentials. Request log: `logs/shopify_req.json`.

Sync history: `sync_sessions` + `sync_rows` tables (with `platform` column and `user_id` audit) record every run; the history panel on `/stocuri` shows the last 10 sessions per platform with a read-only historical view.

### Shopify integration (delivered 2026-06-03)

- `app/automations/stocuri_shopify/api_client.py` — OAuth token cache (24h expiry, auto-refresh, in-memory `_TokenCache` with asyncio.Lock), paginated inventory fetch via `location.inventoryLevels` (50/page), `inventorySetQuantities` mutation (batches of 50)
- `app/automations/stocuri_shopify/orchestrator.py` — `preview()` / `sync()` / `preview_shopify_only()`
- `app/automations/stocuri_shopify/request_logger.py` — rotating JSON log, last 20 entries → `logs/shopify_req.json`, token masked as `***`
- `app/blueprints/stocuri_shopify.py` — `/preview`, `/sync`, `/connection-test`

**Auth:** OAuth client credentials. App "SyncStoc" created in the Shopify Dev Dashboard (not legacy admin). Scopes: `write_inventory, read_inventory, read_locations, read_products`. Token endpoint: `POST https://{shop}/admin/oauth/access_token` with `grant_type=client_credentials`. GraphQL API version `2025-04`.

**Gotchas fixed during delivery (do not reintroduce):**
1. The field on `InventoryLevel` is `item`, not `inventoryItem`
2. `inventorySetQuantities` requires `ignoreCompareQuantity: true` (mandatory since API 2025-04)
3. Switching the platform radio must reset the file input `.value`, or re-selecting the same file fires no change event
4. Safety threshold: stock ≤ threshold is sent as 0; independent per platform (`EMAG_STOCK_SAFETY_THRESHOLD`, `SHOPIFY_STOCK_SAFETY_THRESHOLD`), default 5
5. SKU matching uses `_normalize_sku()` from `csv_filler.py`: strips leading apostrophe + trailing `-XX` suffix; matches `codmare` from the internal report to the Shopify variant SKU

### Connection status cache

`connection_status` table + `app/connection_cache.py` (TTL 3 min) — at most one external eMAG/Shopify API call per platform per window, shared between all users. The `connection-test` routes return `cached` + `checked_at` fields; the connDot tooltip shows check time.

---

## 7. Demand forecasting

The forecast engine, backtest, reorder logic, and AI procurement agent are documented in **`app/forecast/README.md`** — read that first for anything forecast-related.

Quick orientation:
- Package: `app/forecast/` (AutoETS + seasonal overlays, middle-out brand→SKU allocation, reorder with safety stock)
- UI: `/forecast` (5 tabs + AI agent); CLI: `tools/run_forecast.ps1`, `tools/run_backtest.ps1`
- Results tables: `forecasts`, `reorder_suggestions`, `forecast_runs`, `forecast_backtests`; per-brand business rules (lead times, safety stock, seasonal restrictions) in `brands_config`
- Full page audit (architecture, suggestion algorithm, column-by-column reference, API, 20 ranked issues): `docs/analysis/forecast_page_analysis.md` (2026-07-02); open findings tracked in `docs/BACKLOG.md`

---

## 8. Supplier order imports — code mapping (Leonex)

In-transit supplier orders are imported per brand (`etl/import_comenzi_tranzit_*.py`)
into `comenzi_furnizori` + `comenzi_furnizori_linii`, then merged into the
stock/orders view (`/forecast`, Operational → Stoc & comenzi) **by `sku`**.

**Leonex trap:** the Leonex Order Form uses the supplier's own article codes
(`MK…`, e.g. `MK000928`) with English descriptions — these exist nowhere in
Torb's stock, so a line stored under the raw MK code cannot merge and surfaces as
a stray zero-stock row. Fix (delivered 2026-07-03, migration 0014):
`corr_leonex_cod_mapping` maps each `MK…` → Cod TORB (`stoc.cod_mare`, e.g. `584`);
the importer resolves `MK → cod_torb → stoc.sku` and stores each line under the
Torb identity (`cod_furnizor = cod_torb`, `sku`/`descriere` = Torb SKU name).

- The mapping is **seeded once** (10 pairs); it is not auto-derivable — MK codes
  appear in no stock column.
- Lines whose MK code is **not in the mapping are skipped** (not stored) and
  reported via an `AVERTISMENT:` line, surfaced as an amber note in the upload UI
  so a new code can be added to the table.
