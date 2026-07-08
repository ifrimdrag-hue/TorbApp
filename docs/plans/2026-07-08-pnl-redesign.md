# P&L Module — CFO-Grade Redesign Plan

**Date:** 2026-07-08 · **Author:** analysis session with the owner · **Implementer:** Claude Opus
**Status:** approved for implementation phase by phase (F0 first; confirm open questions before F1)

## 0. Context — what exists and what is proven

The P&L module (`app/pnl_import.py`, `app/pnl_logic.py`, `app/queries/pnl.py`, `app/blueprints/pnl.py`, `app/templates/pnl/`) computes a monthly P&L per entity (Torb / Tobra / consolidated Grup) from imported trial balances (.xls, one per entity per month). On 2026-07-08 it was validated against real data — 18 balance files (Tobra full 2025 + Q1 2026, Torb Q1 2026): computed net profit reconciles with the account-121 balance **to the cent** for every period (after migration 0039 mapped 7583/6583).

Key facts about the source files (verified on real exports):
- Header row 0: `cont, dencont, functie, sid, sic, sfd, sfc, contsint, densint, rulld, rullc, rulcd, rulcc`.
- `rulld`/`rullc` are **current-month** turnovers; `rulcd`/`rulcc` are **cumulative** (year-to-date) turnovers. Verified: `rulld(M) == rulcd(M) − rulcd(M−1)` on every account tested.
- Monthly closing is performed: for 7xx accounts `rulcd` equals cumulative revenue (closing debits), which is why the current Δ`rulcd` method reconciles.
- Entity detection: `tobra` in filename → tobra, else torb. Period from filename (`bal 03 2026 tobra.xls`, `01 2026.xls`).

**The owner's core requirements** for this redesign:
1. As complete and as easy to understand/evaluate as possible for a financial/commercial director.
2. Everything starts from balance imports; **balances get corrected and re-sent** — any new import of the same entity+month must **fully replace** the previous one.
3. Possible remapping of accounts into a clearer P&L structure.

---

## 1. Gap analysis (CFO / commercial-director perspective)

Ranked: correctness first, then explainability, then analytical depth.

### C1 — Re-import does not fully replace (correctness, violates owner requirement)
`pnl_balante_raw` has `UNIQUE(entitate, an, luna, cont) ON CONFLICT REPLACE`. Re-importing a corrected balance replaces rows for accounts present in **both** versions, but **rows for accounts that disappeared from the corrected file survive** as ghosts and keep feeding the P&L. Also `INSERT OR REPLACE` churns row ids and any same-key duplicates inside one file are silently collapsed.

### C2 — Monthly figures depend on the prior month being imported (correctness)
`_raw_monthly` = Δ`rulcd`. When month M−1 is missing, month M silently shows the **cumulative** value labeled as monthly (this actually happened: Torb March 2026 displayed cumulative Q1 until Jan+Feb were imported). Silent wrongness is the worst possible behavior for a CFO screen. **The fix is structural, not a warning:** compute monthly values from the month's own `rulld`/`rullc` columns (verified identical to Δ`rulcd`) so each balance is self-sufficient. Keep Δ`rulcd` as an automatic cross-check when the prior month exists.

### C3 — No import-time validation (trust)
Nothing checks that: the balance balances (Σ debit = Σ credit), months chain (`sid/sic(M) == sfd/sfc(M−1)` per account — the fingerprint of "the accountant corrected an earlier month after later months were already imported"), or that the computed P&L reconciles with account 121. The 121 reconciliation was done by hand this session and caught a real 16,426 RON gap; it must be automatic and visible.

### C4 — Consolidated Grup double-counts intra-group trade (correctness of the group view)
`grup` = torb + tobra summed per account. If the two entities trade with each other, group revenue and COGS are both inflated by the intra-group amount. Needs at least a manual monthly elimination entry.

### E1 — OPEX bucket too coarse to steer the business (explainability)
`Servicii terti / logistica / marketing` aggregates 10 synthetic accounts (611, 612, 613, 622, 623, 624, 625, 626, 627, 628): rent + transport + marketing + bank fees in one line. A distribution CFO steers transport cost, marketing spend and admin overhead **separately**. This is the core of the requested remapping (§3).

### E2 — Mapping coverage is reactive (explainability)
Seed covers only the 35 accounts seen so far. Any new account used by the accountants (e.g. 698 microenterprise tax, 654 bad-debt losses, 6812 provisions, 763/768 financial) lands in "unmapped" and silently skips the P&L until someone maps it. The /pnl/mapare screen (added 2026-07-08) makes this visible, but the seed should cover the standard Romanian chart of accounts classes 6–7 up front, with a prefix fallback for analytic accounts.

### E3 — No drill-down (explainability)
A CFO seeing "Servicii terți 202,976" must be able to click and see the accounts behind the number, monthly. The data exists (`pnl_balante_raw` × mapping); only the UI is missing.

### A1 — No month-over-prior-year comparison in the grid (analytics)
The grid shows current-year months only; `data_py` is loaded but used only for alarms. CFO baseline view is CY vs PY per month, Δ%.

### A2 — No budget (analytics, optional)
Actual-only P&L. Target/budget per line per month with variance columns is the natural next step, explicitly out of scope until the owner asks (see F4).

### A3 — Balance sheet data imported but unused (analytics, high leverage)
The same files carry classes 1–5: cash (512x/531x), receivables (4111/491), suppliers (401), inventory (371/378/4428), bank debt (162x/519x). A working-capital dashboard (cash position, DSO/DPO/DIO, net working capital) costs zero new imports. Out of scope until F4, listed so the data model anticipates it (never delete non-6/7 rows on import — keep storing the full balance, as today).

### UX — data freshness & import ergonomics
The /pnl page does not say which months are loaded per entity, nor when they were imported. The Actualizare drop zone (multi-file, added 2026-07-08) is the ingestion path; freshness must be visible where decisions are made, on /pnl.

---

## 2. Design principles

1. **The trial balance is the single source of truth.** No hand-adjustments to imported values; corrections happen in accounting and arrive as re-imports.
2. **Re-import = full replace** of (entitate, an, luna) in one transaction. Deterministic, idempotent, logged.
3. **Every screen reconciles or warns.** The 121 check runs on every import and shows on /pnl. No silently wrong number, ever: a figure that cannot be computed correctly is shown as missing with a reason, not approximated.
4. **Month values come from the month's own file** (`rulld`/`rullc`), so any subset of months can be imported in any order.
5. **Mapping is data, not code.** Editable in UI, changes logged, reconciliation re-checked after every edit. Structure (line order/subtotals) stays in code (`PNL_STRUCTURE`).
6. **Keep storing full balances** (all account classes) — F4 consumes them.

---

## 3. Target P&L structure and remapping (the CFO view)

Stable keys (left) are dict keys in code; Romanian labels (right) are UI text. `line` rows sum mapped accounts; `subtotal`/`pct` rows are computed.

| # | type | key / label | formula or mapped accounts (semn) |
|---|------|-------------|-----------------------------------|
| 1 | line | `venituri_marfa` — Venituri mărfuri | 707 (+) |
| 2 | line | `venituri_servicii` — Venituri servicii & alte activități | 704, 705, 706, 708 (+) |
| 3 | line | `reduceri_acordate` — Reduceri comerciale acordate | 709 (−) |
| 4 | subtotal | `ca_neta` — **CIFRA DE AFACERI NETĂ** | 1+2+3 |
| 5 | line | `cost_marfa` — Cost marfă | 607 (−), 608 (−) |
| 6 | line | `reduceri_primite` — Reduceri comerciale primite | 609 (+) |
| 7 | subtotal | `marja_bruta` — **MARJA BRUTĂ** (+ `marja_bruta_pct`) | 4+5+6 |
| 8 | line | `ch_personal` — Cheltuieli personal | 641, 642, 6421, 6422, 645, 6451, 6452, 6453, 6456, 6457, 6458, 646 (−) |
| 9 | line | `transport_logistica` — Transport & logistică | 624, 6022 (−) |
| 10 | line | `marketing_comercial` — Marketing & protocol | 623 (−) |
| 11 | line | `chirii_utilitati` — Chirii & utilități | 612, 605 (−) |
| 12 | line | `servicii_terti` — Servicii terți & administrativ | 611, 613, 614, 621, 622, 625, 626, 627, 628 (−) |
| 13 | line | `consumabile` — Consumabile & inventar | 6021, 6024, 6028, 603, 604, 606 (−) |
| 14 | line | `impozite_taxe` — Impozite și taxe | 635 (−) |
| 15 | line | `alte_ch_exploatare` — Alte cheltuieli exploatare | 654, 6581, 6582, 6583, 6584, 6585, 6586, 6587, 6588 (−) |
| 16 | line | `alte_ven_exploatare` — Alte venituri exploatare | 711, 741, 754, 758, 7581, 7582, 7583, 7584, 7588 (+) |
| 17 | subtotal | `ebitda` — **EBITDA** (+ `ebitda_pct`) | 7+8+…+16 |
| 18 | line | `amortizare_provizioane` — Amortizare & provizioane | 6811, 6812, 6813, 6814, 6817, 681 (−); 7812, 7813, 7814, 781 (+) |
| 19 | subtotal | `ebit` — **EBIT** | 17+18 |
| 20 | line | `venituri_financiare` — Venituri financiare | 761, 762, 763, 764, 765, 766, 767, 768, 786 (+) |
| 21 | line | `cheltuieli_financiare` — Cheltuieli financiare | 663, 664, 665, 666, 667, 668, 686 (−) |
| 22 | subtotal | `profit_brut` — **PROFIT ÎNAINTE DE IMPOZIT** | 19+20+21 |
| 23 | line | `impozit` — Impozit pe profit / venit | 691, 698 (−) |
| 24 | subtotal | `profit_net` — **PROFIT NET** (+ `profit_net_pct`) | 22+23 |

Remapping notes:
- **Prefix fallback:** exact `cont` match first, then longest mapped prefix (e.g. an analytic `6221` falls back to `622`). The unmapped panel then only shows genuinely unknown accounts. Class 6/7 accounts matched only by an implausibly short prefix (<3 chars) stay unmapped.
- Current custom rows are preserved: migration remaps only seed-known accounts; any cont a user added/edited keeps its assignment (mapping edits carry a flag `sursa='manual'` from F2 on; migration treats pre-existing rows as seed).
- `608` (ambalaje) sits in Cost marfă — packaging follows goods for a distributor. `613` (asigurări) in Servicii terți. Both single-account moves later if the owner prefers.
- % lines (`*_pct`) = value / `ca_neta`, YTD-recomputed as today.
- `pnl_config` alarm rows must be re-seeded onto the new keys (same thresholds, mapped old-line → new-line; the split lines inherit the old bucket's thresholds).

---

## 4. Implementation phases

Each phase is independently shippable, tested, and ends reconciled to 121 on the real 18-file dataset.

### F0 — Correctness foundation (must ship first)

1. **Full-replace import.** In `pnl_import.persist_rows`: same transaction → `DELETE FROM pnl_balante_raw WHERE entitate=? AND an=? AND luna=?` → `executemany INSERT`. Log `status='ok'` with `rows` and `replaced` count (new column or encode in status message). Drop `ON CONFLICT REPLACE` from the unique index (keep the UNIQUE constraint; plain INSERT after DELETE cannot conflict) — migration rebuilds the table (SQLite can't alter constraints).
2. **Monthly from `rulld`/`rullc`.** Parser already stores both. New `queries.pnl_monthly(entitate, an, luna)` returns per cont: `rulld` if the mapped semn is negative (expense nature), `rullc` if positive (revenue nature) — decided per account by its **mapping semn**, not by `functie`. `compute_pnl_month` uses it; no prior-month dependency. Cross-check: when M−1 exists, assert |monthly − Δrulcd| per line < 0.05, else attach a per-line warning (surfaced as ⚠ tooltip in the grid).
3. **Import validations** (run in `import_file`, persisted in `pnl_import_log` — add column `validari TEXT` JSON):
   - `echilibru`: |Σsid−Σsic|, |Σsfd−Σsfc|, |Σrulcd−Σrulcc| < 0.05 → else warning.
   - `inlantuire`: if M−1 imported, per-account `sid/sic(M) == sfd/sfc(M−1)` (tolerance 0.05); mismatch → warning "balanța nu se înlănțuie cu luna anterioară — reimportă lunile următoare corectării".
   - `reconciliere_121`: computed PN YTD (through M) vs `sfc−sfd` of 121 in file M, tolerance 0.05 → status per import.
   - Import always **succeeds** with warnings (data may legitimately be work-in-progress); warnings display in the upload zone (extend the multi-file summary), in `/pnl/import` history, and as the freshness badge state on /pnl.
4. **Freshness header on /pnl.** Per entity: last imported month, import timestamp, 121-reconciliation badge (verde „reconciliat", roșu „diferență X RON", gri „luna precedentă lipsă — verificare parțială"). Missing months in the displayed year render as em-dash columns with tooltip „balanță neîncărcată", never as zero.
5. **Tests:** re-import removes ghost accounts; monthly == Δrulcd on the real-file fixtures; validation trio (construct a broken chain file in-test); 121 badge logic. Keep the existing 4 pnl tests green.

*Acceptance:* re-importing any corrected balance leaves the DB exactly as if only the new file ever existed; every month displays correctly with any subset of months imported; /pnl shows freshness + reconciliation per entity.

### F1 — Remapping & structure v2

1. Migration: replace `PNL_STRUCTURE` (code) with §3; reseed `pnl_mapping_conturi` (full class 6/7 standard chart at synthetic level per §3 table); reseed `pnl_config` onto new keys.
2. Prefix-fallback resolution (in `queries.pnl_mapping` consumer or a resolver util; unit-tested).
3. Excel export (`build_pnl_xlsx`) and alarm config follow the new structure automatically (they read `PNL_STRUCTURE`/`pnl_config`).
4. Re-validate all 18 files: PN unchanged per entity/month (remapping moves lines around but total must still equal 121), diff report printed in the PR description.

*Acceptance:* /pnl shows the v2 lines; unmapped panel empty on the 18-file dataset; PN identical to pre-remap to the cent.

### F2 — Mapping UX (owner-editable)

1. `/pnl/mapare` becomes editable: per row change `pnl_line` (select from structure lines) and `semn`; unmapped panel rows get an inline "mapează pe…" action. POST `/pnl/api/mapping` (single row upsert).
2. `pnl_mapping_log` table (cont, old_line, old_semn, new_line, new_semn, user, timestamp) — written on every edit; shown collapsed at the bottom of the page.
3. After every save: recompute 121 reconciliation for the latest month of each entity, show the result inline (the guard that a bad edit is caught immediately).
4. RBAC: same `pnl` blueprint permission (already gated).

*Acceptance:* the owner can map a new account end-to-end without a developer; every edit is logged and reconciliation-checked.

### F3 — CFO analytics

1. **Comparison modes** on /pnl (selector): Lunar (current) · Lunar vs an precedent (PY value + Δ% under each month) · Cumulat YTD · % din CA (exists). PY data loads only for years present in `pnl_balante_raw`.
2. **Drill-down:** click any line cell → offcanvas/panel: accounts composing the line for that month (cont, dencont, valoare lunară, YTD, Δ vs PY), from `pnl_balante_raw` × mapping. Read-only, links to /pnl/mapare.
3. **Group eliminations:** table `pnl_eliminari (an, luna, venituri REAL, cost REAL, observatii)` + small editor on /pnl (visible in Grup view only). Grup P&L subtracts `venituri` from `venituri_marfa` and adds `cost` back to `cost_marfa`. Default 0 → identical to today. (Owner question Q1 below.)
4. **Coerență comercială:** card on /pnl (Torb view): CA din balanță (707+704+708−709) vs CA din ERP (`tranzactii.val_neta` summed per month) — Δ%; >2% shows warning. Reuses existing tranzactii data; entities without ERP sales data skip the card.

*Acceptance:* a CFO can answer "de ce a crescut transportul în martie?" (drill-down), "cum stăm față de anul trecut?" (comparison), and trust the Grup view (eliminations) without leaving /pnl.

### F4 — Later (explicitly out of scope now; do not build)

- **Buget:** `pnl_buget(an, luna, entitate, pnl_line, valoare)` + xlsx template import + "vs Buget" mode + variance alarms.
- **Bilanț & working capital:** /pnl/bilant from classes 1–5 (cash, clienți net de 491, furnizori, stoc, datorii bancare; DSO/DPO/DIO from CA/COGS). Data already stored.
- PDF one-pager per month.

---

## 5. Open questions — ANSWERED by the owner (2026-07-08)

- **Q1 (F3):** Torb and Tobra are related but **currently do not trade with each other**. Build the manual monthly eliminations editor as designed (defaults 0, so Grup = simple sum until they do trade); lowest priority within F3.
- **Q2 (F1):** **Confirmed** — 612 chirii under „Chirii & utilități"; 608 ambalaje under Cost marfă; 613 asigurări under Servicii terți.
- **Q3 (F1):** Tobra pays **profit tax (691)**. Seed both 691 and 698 anyway (698 stays as safety).
- **Q4 (F3):** **PY value + Δ% beneath each month** (the denser default).

## 6. Conventions for the implementer

- Follow `CLAUDE.md`: ruff-clean, tests in `tests/`, migrations numbered sequentially (`0040+`), CHANGELOG entry per phase, docs update per the updating-documentation skill (BUSINESS_LOGIC §P&L and TECHNICAL §Data after F1).
- UI text Romanian, code/comments English.
- Every phase ends with the 18-file real-data validation (owner's files; ask for them or use the imported local DB) and the 121 reconciliation printed in the summary.
- Do not touch `pnl_app` remnants (already removed at cutover) or the standalone `/pnl/import` page beyond what F2 needs — the Actualizare drop zone is the primary ingestion path.
