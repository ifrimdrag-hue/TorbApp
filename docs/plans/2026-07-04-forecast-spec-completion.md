# Forecast spec completion — plan, checklist & spec digest (2026-07-04)

Source of truth: owner docs `Brief Modul Aprovizionare Torb.docx` + `Specificatie Forecast Torb.docx`
(the docx files are deleted after this session — their essential rules are digested below).
Owner decisions: `app/templates/decision_torb.html`. Prior audit: `docs/analysis/forecast_page_analysis.md`.

Owner answers this session: **scope = lowest-risk subset only**; **keep RO/Export split**;
**OOS = Level-1 heuristic now + start capturing** (DB is rebuilt ~daily — snapshot capture must
survive rebuilds); **new model stays opt-in** (`?model=nou`, default legacy).

---

## A. Shipped this session (low-risk, fully-specified, pure + unit-tested, `nou` path only)

- [x] **OOS/neutral months — Level-1 heuristic** (Brief §4.1): a month where ≥ `prag_neutru_multi_client`
      (70%) of an article's listed clients sold zero → neutral for all the article's pairs; excluded
      from the mean numerator+denominator and pauses the delisting clock.
- [x] **6-month INACTIV global cut** (Spec §7): 0 total sales across the last `taiere_inactiv_luni`
      (6) closed months → article forecast 0 / excluded. Seasonal guard: skip if peak seasonal index ≥ 3.0.
- [x] **DELISTAT label** (Spec §5.2): SUSPECT past `prag + confirmare_delistare_zile` (90d) → DELISTAT.
      Same numeric effect as SUSPECT (contribution 0); label only, for reporting.
- [x] **MOQ floor** (Spec §8): `max(raw, moq)` before bax rounding in `split_with_safety`. Inert until
      MOQ data exists (`produse` has no MOQ column yet).
- [x] **Daily stock-snapshot capture** ETL (`etl/snapshot_stoc.py`): idempotent per date. `stock_snapshot`
      survives the partial rebuild; the OPEN item is just wiring the run into the pipeline (see §C).

## B. Deferred — needs judgment / UI / more scope (present to owner)

- [ ] **New-listing ramp-up** (Spec §6): analogy (article avg × size factor `[0.25,4.0]`), 3-mo blend,
      2× anti-peak cap, `c)` manual estimate flow. Needs listing detection + UI.
- [ ] **Manual delisting confirmation** (Spec §5.2, §10): exception report + Confirmă/Fals-pozitiv
      buttons + persistence table + REACTIVAT→listare-nouă.
- [ ] **"An curent vs. an trecut" sales view** (Brief §9): third toggle option + neutral-month shading.
- [ ] **MOQ data** (decision 6): owner to supply MOQ list per supplier/article.
- [ ] **F2** order lifecycle (statuses, exceptions list, delay alarms 45/10/45), **F3** documents,
      **F4** batch/expiry stock + Alert Center (7 signals). Design data model for all up front.

## C. Data/infra checks the owner/dev must resolve

- [ ] Wire `etl/snapshot_stoc.py` into `rebuild_db.main()` (or a scheduled job) so a dated snapshot is
      captured after each rebuild. `stock_snapshot` survives the partial rebuild (only forecast `--reset`
      drops it), so this is a wiring task, not a data-loss risk.
- [ ] `stock_snapshot` empty → no retroactive OOS; Level-1 heuristic is sales-only, works now.
- [ ] `stoc_expirare` already carries `lot`+`data_expirare` (F4 seed); `comenzi_furnizori(_linii)` seed F2.
- [ ] MOQ + lead time populated per supplier/article (`produse` lacks MOQ column).

## D. Verify after implementation (the "list to check")

- [ ] Spec §11 case 8: `necesar=100×2+25=225; 225−500−200<0 → 0`.
- [ ] Case 4: quarterly client, last buy 5mo ago stays ACTIV (`max(180,3×~90)=270`).
- [ ] Case 6: article listed 4mo ago averages over 4mo, no pre-listing zeros.
- [ ] Seasonal gate at 24mo + cap `[0.2,5.0]`.
- [ ] `?compare=1` on Basilur: old vs new diff sane before any flip.
- [ ] Default is still `model=actual`; toggle flips cleanly.

---

## Spec digest (authoritative rules, so docx can be deleted)

**Model (Spec §2):** demand per client×article; `prognoza_articol = Σ active pairs + baseline_nealocat`.
**Window (§4.1):** `start = max(first_sale, listing_date?, today−36mo)` → last closed month.
**Mean (§4.2):** mean over window, missing months = 0, MINUS OUT_OF_STOCK months.
**Seasonality (§4.3):** article-level `month_mean/overall_mean`, gated off <24mo (→1.0), capped `[0.2,5.0]`.
**OOS (§4.4):** month unavailable ≥50% of working days → OUT_OF_STOCK, excluded from mean.
**Neutral months (Brief §4.1):** unified OOS/gap/block marker; excluded from mean + pauses delisting clock.
Lvl1 = ≥70% active clients zero simultaneously (auto, retroactive, sales-only). Lvl2 = daily stock
snapshot (≥50% days unavailable). Lvl3 = manual events journal (financial/logistic blocks; priority over auto).
**Delisting (§5):** adaptive `prag = max(180, 3×mean_purchase_interval)`. SUSPECT → contribution 0
immediately. DELISTAT = manual confirm OR suspect +90d. REACTIVAT → new-listing flow.
**New listing (§6):** est = article-avg-across-active-clients × size_factor (`vânz_12mo/avg_per_client`,
cap `[0.25,4.0]`); fallback category-at-client; fallback manual. Ramp-up mo1 `.7e+.3r`, mo2 `.4e+.6r`,
mo3 `.2e+.8r`, mo4+ real. Anti-peak: cap mo1 at `2×est`.
**Inactive cut (§7):** 0 sales 6 consecutive months (with stock) → INACTIV, forecast 0. Reactivation →
new-listing. Seasonal items (idx ≥3.0 concentrated) evaluated only vs their season months.
**Order (§8):** `necesar = prognoză_lunară×(lead_luni+acoperire_luni) + coef×prognoză_lunară`;
`brut = necesar − stoc − în_curs`; `final = round_up_bax(max(brut, MOQ))` if brut>0 else 0.
**Recalc (§11):** nightly scheduled job; suggestions on demand.
**Brief F2 alarms:** 45d placed-without-loading / 10d road transit / 45d sea (Basilur). Alarm only marks;
exclusion only by explicit user decision (Anulată / Termen nou).
**Brief F4:** stoc_util = Σ per lot in FEFO order of `min(lot_qty, uncovered_forecast_to_lot_expiry)`;
replaces stoc_curent in §8. Expiry risk report (default 90d), FEFO check on snapshot diffs.
**Brief params to set:** price-diff alert %, dead-stock value lei, notification channel, ERP lot+BBD report.
