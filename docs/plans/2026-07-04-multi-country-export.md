# Multi-country export clients — implementation plan (owner item 2, 2026-07-04)

Owner brief: "vreau sa pot defini manual tara, in fiecare tara clientul sau clientii,
si acestia sa imi apara direct si in tabela de forecast; istoricul separat pentru
fiecare tara cu clientii alocati, la fel ca in modulul RO; exclusi din sugestia de
comanda RO si trecuti fiecare la tara lui." Constraint: **nothing hardcoded** —
countries and client allocations live only in `tari_export` / `clienti_export` (UI-managed).

Owner decisions (asked 2026-07-04):
1. Order quantities are **persisted per country** (not just displayed) → migration.
2. **No stock offset for export countries**: available stock covers RO demand only;
   each export country's suggestion = its full coverage demand (+ safety). This
   replaces the old "surplus offsets export" rule in the NEW model only
   (`model=actual` keeps `_ro_hu_split` unchanged).

## Semantics

- `tari_export.piata` becomes the market key (short code: HU, AT, MD...). The
  special value `RO` still means "domestic bucket" — clients allocated to a
  piata=RO country count in the RO column. The setari modal's fixed RO/HU select
  becomes a free-text short-code input (RO semantics documented in the UI).
- A client in `clienti_export` (activ=1, country activ=1, piata != RO) is
  **excluded from the RO suggestion** and forecast under its country's column.
- Existing data: Ungaria/HU already correct; Austria+Moldova currently sit in
  piata='RO' (the old binary model had nowhere to put them). Owner re-keys them
  from the UI — no data migration of piata values (nothing hardcoded).

## Steps

1. **Migration 0019** — `comenzi_linii_piete(linie_id→comenzi_furnizori_linii.id
   ON DELETE CASCADE, piata TEXT, cantitate INTEGER, UNIQUE(linie_id, piata))`.
   `cantitate_ro`/`cantitate_export` stay as aggregates (compat + reporting).
2. **pair_engine** — `_fetch_rows`: market = active country's piata (JOIN
   clienti_export×tari_export, both activ=1), else 'ro'; piata='RO' maps to 'ro'.
   `article_monthly_profiles`: dynamic per-market bases; output keeps `ro`,
   `export` (= sum of all non-ro markets, back-compat), `total`, plus
   `piete: {piata: {month: qty}}`.
3. **forecast_logic** — `split_with_safety` gains per-country mode per decision 2:
   RO = demand+safety−available (floor 0, MOQ, bax); each country =
   demand+safety (no stock offset), bax-rounded. Returns `suggested_piete`.
   `build_suggestion` + `queries.forecast_stoc_extended` expose
   `avg_piete`/`sug_piete` per item; `suggested_export`/`avg_monthly_hu` stay as
   aggregate fallbacks for the old UI paths.
4. **UI forecast.html** — Stoc (server-rendered) + Sugestie (JS) tables render
   one Avg/Sug column pair per active export piata (list passed from the route /
   API; columns appear only in `?model=nou`). Order-save flow sends
   `cantitati_piete` per line.
5. **Orders API/queries** — `comanda_line_upsert(..., cantitati_piete=None)`
   writes child rows (delete+insert per line); `comanda_get` returns them;
   `api_comanda_create` passes through. `cantitate_export` = sum(non-RO).
6. **setari UI** — piata select → text input (uppercase, 2-4 chars), helper text.
7. **Tests** — pair_engine multi-market fetch/profiles; split per-country math;
   orders round-trip with piete; route smokes.

Status: steps 1-3 first (engine core), then 4-6 (UI/API), tests alongside.
