# Forecast Client × Article — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the procurement forecast from an article-level 3-year mean to a `client × article` model with zero-filled monthly means, gated/capped seasonality, adaptive delisting detection, and a corrected order-quantity formula — shipped behind a compare toggle so numbers are validated before the new model becomes default.

**Architecture:** A new pure-computation module `app/forecast/pair_engine.py` builds per-`(client, article)` monthly series (zeros included), computes article-level seasonality (gated ≥24 mo, capped [0.2, 5.0]), flags delisting suspects (adaptive threshold `max(180d, 3×mean_interval)`), and aggregates active pairs back to the article-level `{sku: {ro, export, total}}` monthly-profile shape the existing consumers already expect. The two existing consumers (`forecast_logic.build_suggestion` → Suggest tab; `queries.forecast_stoc_extended` → Stoc tab) gain a `model` switch: `actual` (today's `_monthly_sales_by_sku`) vs `nou` (pair engine). A new `forecast_config` table + `/forecast/setari` card exposes the parameters. The order formula gains `safety = coef × monthly_forecast` and round-up-to-bax.

**Tech Stack:** Python 3.11, Flask, SQLite (`data/torb.db`), pytest, Jinja2 templates + Bootstrap 5, vanilla JS. Lint: `ruff check .` must pass.

## Global Constraints

- **Lint:** all Python must pass `ruff check .` with zero errors (E401/E402/E701/E702/E722/E741/F401/F841 forbidden). The PostToolUse hook auto-fixes on write.
- **Language:** code/comments/commits in English; every user-facing string (UI labels, badges, tooltips) in Romanian.
- **No `.py` in repo root.** New forecast code → `app/forecast/`; new migration → `migrations/`; new tests → `tests/`.
- **Encoding:** Romanian strings in `.py` must be UTF-8; read `docs/TECHNICAL.md` §Encoding before editing any `.py` with diacritics.
- **DB access pattern:** use `from db import query, query_one` (dict-row helpers) as `forecast_logic.py` does. Keep pure computation separate from DB fetch so functions are unit-testable.
- **Non-breaking:** the `nou` model is opt-in via `?model=nou`; default stays `actual` until the owner validates via the compare view. Never change suggestion numbers on the default path in this plan.
- **Spec source:** `docs/Specificatie Forecast Torb.docx` (v1.0, 04.07.2026). Section refs (§N) below point to it.
- **Parameter defaults (§9), seeded into `forecast_config`:** `fereastra_luni=36`, `sezonalitate_min_luni=24`, `indice_sezonier_min=0.2`, `indice_sezonier_max=5.0`, `prag_delistare_zile=180`, `prag_delistare_mult=3`, `coef_siguranta=0.25`, `perioada_acoperire_luni=1`. (Also seed, for the settings screen but **not wired** this round — they belong to deferred/blocked spec items: `confirmare_delistare_zile=90`, `taiere_inactiv_luni=6`, `oos_prag_pct=50`, `rampup_luni=3`, `plafon_varf_initial=2`, `factor_marime_min=0.25`, `factor_marime_max=4.0`.)

---

## Scope

**In scope (implementable without owner input):** §2/§4.1 pair window, §4.2 mean-with-zeros, §4.3 seasonality gate+cap, §5.1 delisting SUSPECT detection (advisory), §8 (partial: safety=0.25×forecast, configurable coverage, round-up-to-bax; **no** MOQ floor), §9 config, §11 acceptance tests #3/#4/#6/#8 + seasonal part of #2, plus the compare toggle.

**Out of scope (blocked — see `docs/decision.html` items 5–10):** §4.4 out-of-stock month exclusion, §5 full DELISTAT/REACTIVAT lifecycle + manual confirm UI, §6 new-listing ramp-up, §7 INACTIV "with stock" guard, §8 MOQ floor, §10 exceptions-report/new-listing UI.

## File Structure

- `migrations/0017_20260704_forecast_config.py` — Create: `forecast_config` table + seed defaults.
- `app/forecast/config.py` — Create: `get_params()` / `set_param()` typed accessors over `forecast_config`, with hard-coded fallback defaults so callers never crash if a row is missing.
- `app/forecast/pair_engine.py` — Create: pure functions (`build_window`, `monthly_mean_with_zeros`, `seasonal_index`, `delisting_status`) + DB-backed `article_monthly_profiles(furnizor, params)` returning the article-level profile dict + suspect metadata.
- `app/forecast/forecast_logic.py` — Modify: add `split_with_safety()` (safety + bax rounding); add `model` param to `build_suggestion`.
- `app/queries/forecast.py` — Modify: add `model` param to `forecast_stoc_extended`; when `model='nou'`, source profiles + suspect flags from `pair_engine`.
- `app/blueprints/forecast.py` — Modify: read `model`/compare from query args; add `/api/forecast/config` GET+POST.
- `app/templates/forecast.html` — Modify: model toggle, SUSPECT badge, seasonality gating display, suggestion transparency popover, compare columns.
- `app/templates/forecast_setari.html` — Modify: "Parametri forecast" card.
- `tests/test_pair_engine.py`, `tests/test_forecast_reorder.py`, `tests/test_forecast_config.py` — Create.

---

## Task 1: `forecast_config` table + typed accessors

**Files:**
- Create: `migrations/0017_20260704_forecast_config.py`
- Create: `app/forecast/config.py`
- Test: `tests/test_forecast_config.py`

**Interfaces:**
- Produces: `config.get_params() -> dict[str, float]` (all params, DB value or default); `config.set_param(key: str, value: float) -> None`; `config.DEFAULTS: dict[str, float]`.

- [ ] **Step 1: Write the migration**

Follow the existing runner pattern (look at `migrations/0004_20260604_forecast_tables.py` for the `def migrate(conn):` signature the runner calls).

```python
# migrations/0017_20260704_forecast_config.py
"""Add forecast_config key/value table with seeded defaults (§9 of spec)."""

DEFAULTS = {
    "fereastra_luni": 36,
    "sezonalitate_min_luni": 24,
    "indice_sezonier_min": 0.2,
    "indice_sezonier_max": 5.0,
    "prag_delistare_zile": 180,
    "prag_delistare_mult": 3,
    "coef_siguranta": 0.25,
    "perioada_acoperire_luni": 1,
    "confirmare_delistare_zile": 90,
    "taiere_inactiv_luni": 6,
    "oos_prag_pct": 50,
    "rampup_luni": 3,
    "plafon_varf_initial": 2,
    "factor_marime_min": 0.25,
    "factor_marime_max": 4.0,
}


def migrate(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS forecast_config (
            cheie   TEXT PRIMARY KEY,
            valoare REAL NOT NULL
        )
    """)
    for k, v in DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO forecast_config (cheie, valoare) VALUES (?, ?)",
            (k, v),
        )
```

- [ ] **Step 2: Write the accessor with fallback defaults**

```python
# app/forecast/config.py
"""Typed access to forecast_config with hard defaults (§9 of spec)."""
import logging
from db import query, get_db

logger = logging.getLogger(__name__)

DEFAULTS = {
    "fereastra_luni": 36.0, "sezonalitate_min_luni": 24.0,
    "indice_sezonier_min": 0.2, "indice_sezonier_max": 5.0,
    "prag_delistare_zile": 180.0, "prag_delistare_mult": 3.0,
    "coef_siguranta": 0.25, "perioada_acoperire_luni": 1.0,
    "confirmare_delistare_zile": 90.0, "taiere_inactiv_luni": 6.0,
    "oos_prag_pct": 50.0, "rampup_luni": 3.0, "plafon_varf_initial": 2.0,
    "factor_marime_min": 0.25, "factor_marime_max": 4.0,
}


def get_params():
    params = dict(DEFAULTS)
    try:
        for r in query("SELECT cheie, valoare FROM forecast_config"):
            params[r["cheie"]] = float(r["valoare"])
    except Exception:
        logger.warning("forecast_config read failed; using defaults", exc_info=True)
    return params


def set_param(key, value):
    if key not in DEFAULTS:
        raise KeyError(f"unknown forecast param: {key}")
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO forecast_config (cheie, valoare) VALUES (?, ?) "
            "ON CONFLICT(cheie) DO UPDATE SET valoare=excluded.valoare",
            (key, float(value)),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_forecast_config.py
from forecast import config


def test_defaults_present_when_db_empty(monkeypatch):
    monkeypatch.setattr(config, "query", lambda *a, **k: [])
    p = config.get_params()
    assert p["coef_siguranta"] == 0.25
    assert p["fereastra_luni"] == 36.0


def test_db_overrides_default(monkeypatch):
    monkeypatch.setattr(
        config, "query",
        lambda *a, **k: [{"cheie": "coef_siguranta", "valoare": 0.4}],
    )
    assert config.get_params()["coef_siguranta"] == 0.4


def test_set_param_rejects_unknown_key():
    import pytest
    with pytest.raises(KeyError):
        config.set_param("nope", 1)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_forecast_config.py -v`
Expected: 3 passed. (The migration applies automatically on next Flask start; to apply now for manual checks run `python -c "from migrations.runner import run; run()"` from the project root if the runner exposes `run` — otherwise start the app once.)

- [ ] **Step 5: Commit**

```bash
git add migrations/0017_20260704_forecast_config.py app/forecast/config.py tests/test_forecast_config.py
git commit -m "feat(forecast): add forecast_config table + typed param accessors"
```

---

## Task 2: Pair window + mean-with-zeros (§4.1, §4.2)

**Files:**
- Create: `app/forecast/pair_engine.py`
- Test: `tests/test_pair_engine.py`

**Interfaces:**
- Produces:
  - `build_window(first_sale: date, today: date, window_months: int) -> list[tuple[int,int]]` — list of `(year, month)` from `max(first_sale, today−window_months)`'s month through the last **closed** month (i.e. excludes the current, still-open month).
  - `monthly_mean_with_zeros(pair_months: dict[tuple[int,int], float], window: list[tuple[int,int]]) -> float` — sum of qty over window months (missing = 0) divided by `len(window)`; returns 0.0 if window empty.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_pair_engine.py
from datetime import date
from forecast import pair_engine as pe


def test_window_clips_to_first_sale_not_36mo():
    # First sale 4 months ago -> window is 4 closed months, not 36.
    today = date(2026, 7, 15)
    first = date(2026, 3, 10)
    win = pe.build_window(first, today, window_months=36)
    assert win == [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]


def test_window_capped_at_window_months():
    today = date(2026, 7, 15)
    first = date(2020, 1, 1)
    win = pe.build_window(first, today, window_months=36)
    assert len(win) == 36
    assert win[-1] == (2026, 6)   # last closed month
    assert win[0] == (2023, 7)


def test_mean_with_zeros_declines_toward_zero():
    # Sold 100 in one month, nothing since -> mean over 4 months = 25.
    window = [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]
    pair = {(2026, 3): 100.0}
    assert pe.monthly_mean_with_zeros(pair, window) == 25.0


def test_mean_empty_window_is_zero():
    assert pe.monthly_mean_with_zeros({(2026, 3): 5}, []) == 0.0
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_pair_engine.py -v`
Expected: FAIL (`AttributeError: module 'forecast.pair_engine' has no attribute 'build_window'`).

- [ ] **Step 3: Implement**

```python
# app/forecast/pair_engine.py
"""Client x article forecast core (spec §2, §4, §5).

Pure functions operate on in-memory month->qty dicts so they are unit
testable; article_monthly_profiles() adds the DB fetch + aggregation.
"""
from __future__ import annotations
from datetime import date


def _month_add(y, m, delta):
    idx = (y * 12 + (m - 1)) + delta
    return idx // 12, idx % 12 + 1


def build_window(first_sale, today, window_months):
    """[start ... last closed month] as (year, month) tuples."""
    # Last closed month = month before the current (open) one.
    last_y, last_m = _month_add(today.year, today.month, -1)
    cap_y, cap_m = _month_add(today.year, today.month, -int(window_months))
    fs_y, fs_m = first_sale.year, first_sale.month
    # start = max(first_sale month, cap month)
    if (fs_y, fs_m) >= (cap_y, cap_m):
        start_y, start_m = fs_y, fs_m
    else:
        start_y, start_m = cap_y, cap_m
    if (start_y, start_m) > (last_y, last_m):
        return []
    out = []
    y, m = start_y, start_m
    while (y, m) <= (last_y, last_m):
        out.append((y, m))
        y, m = _month_add(y, m, 1)
    return out


def monthly_mean_with_zeros(pair_months, window):
    if not window:
        return 0.0
    total = sum(pair_months.get(ym, 0.0) for ym in window)
    return total / len(window)
```

- [ ] **Step 4: Run to confirm pass**

Run: `python -m pytest tests/test_pair_engine.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/forecast/pair_engine.py tests/test_pair_engine.py
git commit -m "feat(forecast): pair window + mean-with-zeros (spec 4.1/4.2)"
```

---

## Task 3: Seasonality index — gate + cap (§4.3)

**Files:**
- Modify: `app/forecast/pair_engine.py`
- Test: `tests/test_pair_engine.py`

**Interfaces:**
- Produces: `seasonal_index(article_month_qty: dict[tuple[int,int], float], min_history_months: float, cap_lo: float, cap_hi: float) -> dict[int, float]` — returns `{1..12: index}`. If distinct months of history `< min_history_months` → all `1.0`. Otherwise index[m] = (mean qty in calendar month m) / (overall monthly mean), clamped to `[cap_lo, cap_hi]`.

- [ ] **Step 1: Write failing tests**

```python
def test_seasonality_flat_below_min_history():
    # 12 months of data < 24 -> no adjustment.
    qty = {(2025, m): 10.0 for m in range(1, 13)}
    idx = pe.seasonal_index(qty, min_history_months=24, cap_lo=0.2, cap_hi=5.0)
    assert set(idx.values()) == {1.0}


def test_seasonality_peaks_and_caps():
    # 36 months: Nov huge, rest ~1. Index for Nov must be capped at 5.0.
    qty = {}
    for y in (2023, 2024, 2025):
        for m in range(1, 13):
            qty[(y, m)] = 1.0
        qty[(y, 11)] = 1000.0
    idx = pe.seasonal_index(qty, min_history_months=24, cap_lo=0.2, cap_hi=5.0)
    assert idx[11] == 5.0
    assert 0.2 <= idx[1] <= 1.0
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_pair_engine.py -k seasonality -v`
Expected: FAIL (no attribute `seasonal_index`).

- [ ] **Step 3: Implement (append to `pair_engine.py`)**

```python
def seasonal_index(article_month_qty, min_history_months, cap_lo, cap_hi):
    if len(article_month_qty) < min_history_months:
        return {m: 1.0 for m in range(1, 13)}
    by_month = {m: [] for m in range(1, 13)}
    for (_, m), q in article_month_qty.items():
        by_month[m].append(q)
    month_mean = {m: (sum(v) / len(v) if v else 0.0) for m, v in by_month.items()}
    overall = sum(month_mean.values()) / 12
    if overall <= 0:
        return {m: 1.0 for m in range(1, 13)}
    out = {}
    for m in range(1, 13):
        idx = month_mean[m] / overall
        out[m] = min(cap_hi, max(cap_lo, idx))
    return out
```

- [ ] **Step 4: Run to confirm pass**

Run: `python -m pytest tests/test_pair_engine.py -k seasonality -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/forecast/pair_engine.py tests/test_pair_engine.py
git commit -m "feat(forecast): seasonality index with 24-mo gate + [0.2,5.0] cap (spec 4.3)"
```

---

## Task 4: Delisting SUSPECT detection (§5.1)

**Files:**
- Modify: `app/forecast/pair_engine.py`
- Test: `tests/test_pair_engine.py`

**Interfaces:**
- Produces: `delisting_status(purchase_dates: list[date], today: date, min_days: float, mult: float) -> dict` returning `{"status": "ACTIV"|"SUSPECT", "days_since_last": int, "mean_interval": float|None, "prag": float}`. Threshold `prag = max(min_days, mult × mean_interval)`; if `days_since_last > prag` → `SUSPECT`. With <2 purchases, `mean_interval=None` and threshold falls back to `min_days`.

- [ ] **Step 1: Write failing tests (acceptance #3 & #4)**

```python
def test_delisting_monthly_client_stops_becomes_suspect():
    # Ordered monthly, last purchase 7 months ago -> SUSPECT (case #3).
    today = date(2026, 7, 15)
    dates = [date(2025, m, 1) for m in range(1, 13)]  # last = 2025-12-01
    r = pe.delisting_status(dates, today, min_days=180, mult=3)
    assert r["status"] == "SUSPECT"


def test_delisting_quarterly_client_stays_active():
    # Quarterly buyer, last purchase 5 months ago -> ACTIV (case #4).
    # mean interval ~90d -> prag = max(180, 3*90=270) = 270; 150d < 270.
    today = date(2026, 7, 15)
    dates = [date(2025, 1, 1), date(2025, 4, 1), date(2025, 7, 1),
             date(2025, 10, 1), date(2026, 2, 15)]
    r = pe.delisting_status(dates, today, min_days=180, mult=3)
    assert r["status"] == "ACTIV"
    assert r["prag"] == 270.0
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_pair_engine.py -k delisting -v`
Expected: FAIL (no attribute `delisting_status`).

- [ ] **Step 3: Implement (append to `pair_engine.py`)**

```python
def delisting_status(purchase_dates, today, min_days, mult):
    if not purchase_dates:
        return {"status": "ACTIV", "days_since_last": None,
                "mean_interval": None, "prag": float(min_days)}
    ordered = sorted(purchase_dates)
    days_since_last = (today - ordered[-1]).days
    if len(ordered) >= 2:
        gaps = [(ordered[i] - ordered[i - 1]).days for i in range(1, len(ordered))]
        mean_interval = sum(gaps) / len(gaps)
        prag = max(float(min_days), mult * mean_interval)
    else:
        mean_interval = None
        prag = float(min_days)
    status = "SUSPECT" if days_since_last > prag else "ACTIV"
    return {"status": status, "days_since_last": days_since_last,
            "mean_interval": mean_interval, "prag": prag}
```

- [ ] **Step 4: Run to confirm pass**

Run: `python -m pytest tests/test_pair_engine.py -k delisting -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/forecast/pair_engine.py tests/test_pair_engine.py
git commit -m "feat(forecast): adaptive delisting SUSPECT detection (spec 5.1)"
```

---

## Task 5: Article aggregation → `article_monthly_profiles` (§2)

**Files:**
- Modify: `app/forecast/pair_engine.py`
- Test: `tests/test_pair_engine.py`

**Interfaces:**
- Consumes: `build_window`, `monthly_mean_with_zeros`, `seasonal_index`, `delisting_status` (Tasks 2–4); `config.get_params()` (Task 1).
- Produces: `article_monthly_profiles(furnizor: str, params: dict, today: date|None=None, _rows=None) -> dict[str, dict]`. Each value:
  ```
  {
    "ro": {1..12: float}, "export": {1..12: float}, "total": {1..12: float},
    "cod_produs": str|None,
    "suspects": [ {"cod_client": str, "client": str, "days_since_last": int,
                   "mean_interval": float|None} ],
    "n_active": int, "n_suspect": int,
  }
  ```
  The `ro`/`export`/`total` dicts are **12-month profiles** = `base_monthly_market × seasonal_index[m]`, so they drop straight into the existing `_ro_hu_split` / `_coverage_demand`. `base_monthly_market` = Σ over ACTIVE pairs of that market's `monthly_mean_with_zeros`. SUSPECT pairs contribute 0.

  The `_rows` param injects synthetic transaction rows in tests (bypasses DB). Each row: `{"cod_client","client","sku","cod_produs","market","d": date, "qty": float}` where `market` is `"export"` or `"ro"`.

- [ ] **Step 1: Write failing test (acceptance #6 — 4-month listing averaged over 4, not 36)**

```python
def test_article_profile_new_listing_uses_short_window(monkeypatch):
    today = date(2026, 7, 15)
    params = {"fereastra_luni": 36, "sezonalitate_min_luni": 24,
              "indice_sezonier_min": 0.2, "indice_sezonier_max": 5.0,
              "prag_delistare_zile": 180, "prag_delistare_mult": 3}
    # One RO client, first sale 4 closed months ago, 100/mo each of 4 months.
    rows = []
    for (y, m) in [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]:
        rows.append({"cod_client": "C1", "client": "Client 1", "sku": "S",
                     "cod_produs": "100", "market": "ro",
                     "d": date(y, m, 10), "qty": 100.0})
    prof = pe.article_monthly_profiles("X", params, today=today, _rows=rows)
    # <24 mo history -> seasonal index 1.0; base = 400/4 = 100.
    assert round(prof["S"]["ro"][7], 1) == 100.0
    assert prof["S"]["n_active"] == 1


def test_article_profile_excludes_suspect_client(monkeypatch):
    today = date(2026, 7, 15)
    params = {"fereastra_luni": 36, "sezonalitate_min_luni": 24,
              "indice_sezonier_min": 0.2, "indice_sezonier_max": 5.0,
              "prag_delistare_zile": 180, "prag_delistare_mult": 3}
    rows = []
    # Active client, monthly Jan-Jun 2026.
    for m in range(1, 7):
        rows.append({"cod_client": "A", "client": "Activ", "sku": "S",
                     "cod_produs": "100", "market": "ro",
                     "d": date(2026, m, 10), "qty": 50.0})
    # Suspect client, last buy 2025-01 (>>270d ago).
    rows.append({"cod_client": "B", "client": "Plecat", "sku": "S",
                 "cod_produs": "100", "market": "ro",
                 "d": date(2025, 1, 10), "qty": 999.0})
    prof = pe.article_monthly_profiles("X", params, today=today, _rows=rows)
    assert prof["S"]["n_suspect"] == 1
    # Suspect contributes 0 -> only client A's base counts.
    assert prof["S"]["ro"][7] > 0
    assert prof["S"]["suspects"][0]["cod_client"] == "B"
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_pair_engine.py -k article_profile -v`
Expected: FAIL (no attribute `article_monthly_profiles`).

- [ ] **Step 3: Implement**

Add the DB fetch helper and the aggregator. The DB query groups `tranzactii` by client × sku × (year, month), tagging market via `clienti_export` (mirrors `_monthly_sales_by_sku`). Keep the SQL out of the pure path by routing through `_rows`.

```python
from collections import defaultdict
from db import query


def _fetch_rows(furnizor, cutoff_year):
    export_clause = ("cod_client IN (SELECT cod_client FROM clienti_export "
                     "WHERE activ = 1)")
    sql = f"""
        SELECT cod_client, MAX(client) AS client, sku,
               MAX(cod_produs) AS cod_produs, data_dl,
               CASE WHEN {export_clause} THEN 'export' ELSE 'ro' END AS market,
               SUM(cantitate) AS qty
        FROM tranzactii
        WHERE furnizor = :f AND an >= :cutoff AND data_dl IS NOT NULL
              AND cod_client IS NOT NULL
        GROUP BY cod_client, sku, market, data_dl
    """
    from datetime import date as _d
    out = []
    for r in query(sql, {"f": furnizor, "cutoff": cutoff_year}):
        try:
            y, m, dd = (int(x) for x in str(r["data_dl"])[:10].split("-"))
            d = _d(y, m, dd)
        except (ValueError, TypeError):
            continue
        out.append({"cod_client": r["cod_client"], "client": r["client"],
                    "sku": r["sku"], "cod_produs": r["cod_produs"],
                    "market": r["market"], "d": d, "qty": r["qty"] or 0.0})
    return out


def article_monthly_profiles(furnizor, params, today=None, _rows=None):
    from .forecast_logic import _normalize_sku
    today = today or date.today()
    window_months = int(params["fereastra_luni"])
    rows = _rows if _rows is not None else _fetch_rows(
        furnizor, today.year - (window_months // 12) - 1)

    # Group: sku -> client -> market -> {(y,m): qty}; and purchase dates.
    grp = defaultdict(lambda: defaultdict(lambda: defaultdict(
        lambda: defaultdict(float))))
    pdates = defaultdict(lambda: defaultdict(list))   # sku -> client -> [date]
    first_sale = defaultdict(lambda: defaultdict(lambda: date.max))
    cod_of = {}
    name_of = {}
    art_month_qty = defaultdict(lambda: defaultdict(float))  # sku -> (y,m)->qty
    for r in rows:
        sku = _normalize_sku(r["sku"])
        c = r["cod_client"]
        ym = (r["d"].year, r["d"].month)
        grp[sku][c][r["market"]][ym] += r["qty"]
        pdates[sku][c].append(r["d"])
        if r["d"] < first_sale[sku][c]:
            first_sale[sku][c] = r["d"]
        cod_of.setdefault(sku, r.get("cod_produs"))
        name_of[(sku, c)] = r.get("client") or c
        art_month_qty[sku][ym] += r["qty"]

    result = {}
    for sku, clients in grp.items():
        s_idx = seasonal_index(
            art_month_qty[sku], params["sezonalitate_min_luni"],
            params["indice_sezonier_min"], params["indice_sezonier_max"])
        base = {"ro": 0.0, "export": 0.0}
        suspects, n_active = [], 0
        for c, markets in clients.items():
            ds = delisting_status(pdates[sku][c], today,
                                  params["prag_delistare_zile"],
                                  params["prag_delistare_mult"])
            if ds["status"] == "SUSPECT":
                suspects.append({"cod_client": c, "client": name_of[(sku, c)],
                                 "days_since_last": ds["days_since_last"],
                                 "mean_interval": ds["mean_interval"]})
                continue
            n_active += 1
            win = build_window(first_sale[sku][c], today, window_months)
            for mkt in ("ro", "export"):
                if mkt in markets:
                    base[mkt] += monthly_mean_with_zeros(markets[mkt], win)
        ro = {m: base["ro"] * s_idx[m] for m in range(1, 13)}
        exp = {m: base["export"] * s_idx[m] for m in range(1, 13)}
        result[sku] = {
            "ro": ro, "export": exp,
            "total": {m: ro[m] + exp[m] for m in range(1, 13)},
            "cod_produs": cod_of.get(sku),
            "suspects": suspects, "n_active": n_active,
            "n_suspect": len(suspects),
        }
    return result
```

- [ ] **Step 4: Run to confirm pass**

Run: `python -m pytest tests/test_pair_engine.py -v`
Expected: all passed (window, mean, seasonality, delisting, article_profile).

- [ ] **Step 5: Commit**

```bash
git add app/forecast/pair_engine.py tests/test_pair_engine.py
git commit -m "feat(forecast): aggregate active pairs to article profiles + suspects (spec 2)"
```

---

## Task 6: Order formula — safety + coverage + round-up-to-bax (§8)

**Files:**
- Modify: `app/forecast/forecast_logic.py`
- Test: `tests/test_forecast_reorder.py`

**Interfaces:**
- Consumes: existing `_coverage_demand(monthly_avg, lead_time_days)` (already sums lead+30d; we generalize the safety part separately).
- Produces:
  - `_coverage_demand(monthly_avg, lead_time_days, coverage_days=SAFETY_DAYS)` — add the optional `coverage_days` arg (defaults to `SAFETY_DAYS=30` so existing callers are unchanged).
  - `round_up_to_bax(qty: float, buc_cutie: int|None) -> int` — ceil to the next multiple of `buc_cutie`; if falsy, `int(round(qty))`.
  - `split_with_safety(monthly_ro, monthly_export, lead_days, available, base_ro, base_export, coef, coverage_days, buc_cutie) -> dict` — like `_ro_hu_split` but adds `safety = coef × base_market` to each market's demand before subtracting `available`, then rounds each suggestion up to bax. Returns the same keys as `_ro_hu_split` plus `safety_ro`, `safety_export`.

- [ ] **Step 1: Write failing tests (acceptance #8)**

```python
# tests/test_forecast_reorder.py
from forecast import forecast_logic as fl


def test_round_up_to_bax():
    assert fl.round_up_to_bax(7, 12) == 12
    assert fl.round_up_to_bax(13, 12) == 24
    assert fl.round_up_to_bax(24, 12) == 24
    assert fl.round_up_to_bax(7.4, None) == 7


def test_case8_stock_covers_no_order():
    # Forecast 100/mo, lead 1 mo, coverage 1 mo, safety 0.25*100=25.
    # necesar = 100*2 + 25 = 225; available 500+200=700 -> suggestion 0.
    monthly = {m: 100.0 for m in range(1, 13)}
    r = fl.split_with_safety(
        monthly_ro=monthly, monthly_export={m: 0 for m in range(1, 13)},
        lead_days=30, available=700, base_ro=100.0, base_export=0.0,
        coef=0.25, coverage_days=30, buc_cutie=1)
    assert r["suggested_ro"] == 0


def test_safety_adds_to_demand():
    monthly = {m: 100.0 for m in range(1, 13)}
    r = fl.split_with_safety(
        monthly_ro=monthly, monthly_export={m: 0 for m in range(1, 13)},
        lead_days=30, available=0, base_ro=100.0, base_export=0.0,
        coef=0.25, coverage_days=30, buc_cutie=1)
    # ~ two months demand (200) + safety 25 = ~225, rounded.
    assert 220 <= r["suggested_ro"] <= 232
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_forecast_reorder.py -v`
Expected: FAIL (`round_up_to_bax`/`split_with_safety` missing).

- [ ] **Step 3: Implement (in `forecast_logic.py`)**

Change the `_coverage_demand` signature and add the two new functions:

```python
def _coverage_demand(monthly_avg: dict, lead_time_days: int,
                     coverage_days: int = SAFETY_DAYS) -> float:
    today = datetime.date.today()
    end = today + datetime.timedelta(days=lead_time_days + coverage_days)
    # ... body unchanged ...
```

```python
import math


def round_up_to_bax(qty: float, buc_cutie) -> int:
    if not buc_cutie or buc_cutie <= 0:
        return int(round(qty))
    return int(math.ceil(qty / buc_cutie) * buc_cutie)


def split_with_safety(monthly_ro, monthly_export, lead_days, available,
                      base_ro, base_export, coef, coverage_days, buc_cutie):
    demand_ro = _coverage_demand(monthly_ro, lead_days, coverage_days)
    demand_export = _coverage_demand(monthly_export, lead_days, coverage_days)
    safety_ro = coef * base_ro
    safety_export = coef * base_export
    need_ro = demand_ro + safety_ro
    raw_ro = max(0.0, need_ro - available)
    surplus = max(0.0, available - need_ro)
    raw_export = max(0.0, (demand_export + safety_export) - surplus)
    return {
        "demand_ro": demand_ro, "demand_export": demand_export,
        "safety_ro": safety_ro, "safety_export": safety_export,
        "suggested_ro": round_up_to_bax(raw_ro, buc_cutie),
        "suggested_export": round_up_to_bax(raw_export, buc_cutie),
    }
```

- [ ] **Step 4: Run to confirm pass**

Run: `python -m pytest tests/test_forecast_reorder.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/forecast/forecast_logic.py tests/test_forecast_reorder.py
git commit -m "feat(forecast): safety=coef*forecast + round-up-to-bax order formula (spec 8)"
```

---

## Task 7: Wire the `nou` model into `build_suggestion` (Suggest tab)

**Files:**
- Modify: `app/forecast/forecast_logic.py` (`build_suggestion`)
- Modify: `app/blueprints/forecast.py` (`api_forecast_suggest`)
- Test: `tests/test_forecast_reorder.py`

**Interfaces:**
- Consumes: `pair_engine.article_monthly_profiles`, `config.get_params`, `split_with_safety` (Tasks 5, 6, 1).
- Produces: `build_suggestion(furnizor, min_velocity=1.0, only_needed=True, model="actual")`. When `model="nou"`: source `monthly_data` from `article_monthly_profiles`; compute suggestions via `split_with_safety` (coef, coverage from params; `buc_cutie` from `produse`); attach `n_suspect`/`suspects` to each item. Item dict keeps all existing keys so the template is backward-compatible; adds `n_suspect` (int) and `suspects` (list).

- [ ] **Step 1: Write failing test**

```python
def test_build_suggestion_accepts_model_param(monkeypatch):
    from forecast import forecast_logic as fl

    def fake_profiles(furnizor, params, today=None, _rows=None):
        prof = {m: 10.0 for m in range(1, 13)}
        return {"SKU-Z": {"ro": prof, "export": {m: 0 for m in range(1, 13)},
                          "total": prof, "cod_produs": "100",
                          "suspects": [], "n_active": 1, "n_suspect": 0}}

    monkeypatch.setattr("forecast.pair_engine.article_monthly_profiles",
                        fake_profiles)
    monkeypatch.setattr(fl, "get_in_transit", lambda f: {})
    monkeypatch.setattr(fl, "_listing_changes", lambda f: {})
    monkeypatch.setattr(fl, "get_lead_time",
                        lambda f: {"zile_livrare": 30, "sezon_craciun": 0})
    monkeypatch.setattr(fl, "query", lambda *a, **k: [])
    monkeypatch.setattr(fl, "query_one", lambda *a, **k: {"d": None})
    res = fl.build_suggestion("AnyBrand", min_velocity=0, only_needed=False,
                              model="nou")
    assert res["items"][0]["n_suspect"] == 0
```

- [ ] **Step 2: Run to confirm failure**

Run: `python -m pytest tests/test_forecast_reorder.py -k model_param -v`
Expected: FAIL (`build_suggestion() got unexpected keyword 'model'`).

- [ ] **Step 3: Implement**

In `build_suggestion`, branch on `model`:
- `model="actual"` (default): keep current body verbatim.
- `model="nou"`:
  - `params = config.get_params()`
  - `profiles = pair_engine.article_monthly_profiles(furnizor, params)`; use it in place of `_monthly_sales_by_sku(furnizor)` (same `{sku: {ro,export,total,...}}` shape).
  - fetch `buc_cutie` per sku once: `bax = {r['sku']: r['buc_cutie'] for r in query("SELECT sku, buc_cutie FROM produse WHERE furnizor=:f", {'f': furnizor})}`.
  - replace the `_ro_hu_split(...)` call with:
    ```python
    base_ro = sum(sku_monthly_ro.values()) / 12
    base_export = sum(sku_monthly_export.values()) / 12
    split = split_with_safety(
        sku_monthly_ro, sku_monthly_export, lead_days, available,
        base_ro, base_export, params["coef_siguranta"],
        int(params["perioada_acoperire_luni"] * 30), bax.get(sku))
    ```
  - set `item['n_suspect'] = sku_data.get('n_suspect', 0)` and `item['suspects'] = sku_data.get('suspects', [])`.

Add imports at top: `from forecast import pair_engine, config` (or local imports to avoid cycles — `forecast_logic` is imported by `pair_engine`, so **import `pair_engine`/`config` lazily inside the `model="nou"` branch** to avoid a circular import).

In `api_forecast_suggest` (blueprint), read the model:
```python
model = 'nou' if request.args.get('model') == 'nou' else 'actual'
result = forecast_logic.build_suggestion(furnizor, min_velocity=min_velocity,
                                         only_needed=only_needed, model=model)
```

- [ ] **Step 4: Run to confirm pass + full suite**

Run: `python -m pytest tests/test_forecast_reorder.py -v && ruff check .`
Expected: passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/forecast/forecast_logic.py app/blueprints/forecast.py tests/test_forecast_reorder.py
git commit -m "feat(forecast): wire client-article model behind ?model=nou in build_suggestion"
```

---

## Task 8: Wire the `nou` model + suspect flag into the Stoc tab

**Files:**
- Modify: `app/queries/forecast.py` (`forecast_stoc_extended`)
- Modify: `app/blueprints/forecast.py` (`forecast` route passes `model`)
- Test: manual (this function is DB-heavy; covered by acceptance via UI)

**Interfaces:**
- Consumes: `pair_engine.article_monthly_profiles`, `config.get_params`, `forecast_logic.split_with_safety`.
- Produces: `forecast_stoc_extended(..., model="actual")`. When `model="nou"`: build `profiles = article_monthly_profiles(furnizor_or_None, params)` **once per furnizor present** (reuse the existing `monthly_cache` dict, but populate it from the pair engine instead of `_monthly_sales_by_sku`); compute `suggested_ro/hu` via `split_with_safety`; attach `r['n_suspect']` per row.

- [ ] **Step 1: Add the `model` arg + branch**

In `forecast_stoc_extended`, add `model="actual"` param. Where `monthly_cache[f] = forecast_logic._monthly_sales_by_sku(f)` is built (≈ line 257), branch:
```python
if model == "nou":
    from forecast import pair_engine, config as fc_config
    params = fc_config.get_params()
    for f in furnizori_in_rows:
        monthly_cache[f] = pair_engine.article_monthly_profiles(f, params)
else:
    for f in furnizori_in_rows:
        monthly_cache[f] = forecast_logic._monthly_sales_by_sku(f)
```
In the per-row loop, when `model == "nou"`, replace the `_ro_hu_split(...)` call with `split_with_safety(...)` (same argument construction as Task 7, `buc_cutie` fetched per furnizor into a `bax` dict), and set `r['n_suspect'] = sku_data.get('n_suspect', 0)`. Guard the synthetic-row branches (transit-only, sold-no-stock) the same way, or leave them on `_ro_hu_split` when `model='actual'`.

- [ ] **Step 2: Pass `model` from the route**

In the `forecast` view (blueprint) read `model = 'nou' if request.args.get('model') == 'nou' else 'actual'` and pass it to `queries.forecast_stoc_extended(...)`; also pass `model` and a `compare` flag into `render_template`.

- [ ] **Step 3: Smoke-test the branch**

Run (from project root, needs a populated `data/torb.db`):
```bash
python -c "import sys; sys.path.insert(0,'app'); import queries; rows=queries.forecast_stoc_extended(model='nou'); print(len(rows), 'rows'); print([r.get('n_suspect') for r in rows[:5]])"
```
Expected: prints a row count and a list of integers (no exception). If the DB is unavailable in this environment, instead run `ruff check app/queries/forecast.py` and verify the branch parses.

- [ ] **Step 4: Lint**

Run: `ruff check .`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add app/queries/forecast.py app/blueprints/forecast.py
git commit -m "feat(forecast): source Stoc tab from client-article model under ?model=nou"
```

---

## Task 9: Config screen on `/forecast/setari` (§9 frontend + API)

**Files:**
- Modify: `app/blueprints/forecast.py` (add `/api/forecast/config` GET+POST; pass params to `forecast_setari`)
- Modify: `app/templates/forecast_setari.html` (add "Parametri forecast" card)
- Test: `tests/test_forecast_config.py` (extend)

**Interfaces:**
- Consumes: `config.get_params`, `config.set_param`.
- Produces: `GET /api/forecast/config` → `{"ok": True, "params": {...}}`; `POST /api/forecast/config` body `{"cheie": str, "valoare": number}` → `{"ok": True}` (400 on unknown key).

- [ ] **Step 1: Add the API endpoints (blueprint)**

```python
@forecast_bp.route('/api/forecast/config', methods=['GET'])
def api_forecast_config_get():
    from forecast import config as fc_config
    return jsonify({'ok': True, 'params': fc_config.get_params()})


@forecast_bp.route('/api/forecast/config', methods=['POST'])
def api_forecast_config_set():
    from forecast import config as fc_config
    d = request.get_json(silent=True) or {}
    try:
        fc_config.set_param(d['cheie'], float(d['valoare']))
        return jsonify({'ok': True})
    except (KeyError, TypeError, ValueError) as e:
        logger.exception("api_forecast_config_set failed")
        return jsonify({'error': str(e)}), 400
```

- [ ] **Step 2: Pass params to the settings template**

In `forecast_setari` view: `from forecast import config as fc_config` then add `params=fc_config.get_params()` to the `render_template` call.

- [ ] **Step 3: Add the "Parametri forecast" card (template)**

Append a Bootstrap card to `forecast_setari.html` (Romanian labels), one numeric input per wired param, each `onchange` POSTing to `/api/forecast/config`. Wired params to expose now: Fereastră istorică (luni), Istoric minim sezonalitate (luni), Plafon indice sezonier min, Plafon indice sezonier max, Prag delistare (zile), Multiplicator interval delistare, Coeficient stoc siguranță, Perioadă acoperire (luni). Example row markup:
```html
<div class="col-md-4">
  <label class="form-label small">Coeficient stoc de siguranță</label>
  <input type="number" step="0.05" class="form-control form-control-sm cfg-param"
         data-cheie="coef_siguranta" value="{{ params.coef_siguranta }}">
</div>
```
Plus a small script:
```html
<script>
document.querySelectorAll('.cfg-param').forEach(el => {
  el.addEventListener('change', () => {
    fetch('/api/forecast/config', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({cheie: el.dataset.cheie, valoare: parseFloat(el.value)})})
      .then(r => r.json())
      .then(j => { if (!j.ok) AppError.show(j.error || 'Salvare eșuată'); });
  });
});
</script>
```
(Per `docs/TECHNICAL.md` §Frontend conventions: surface errors via `AppError.show()`.)

- [ ] **Step 4: Extend the config test**

```python
def test_set_param_roundtrip_known_key(monkeypatch):
    saved = {}
    class FakeConn:
        def execute(self, *a): saved['args'] = a
        def commit(self): saved['committed'] = True
        def close(self): pass
    monkeypatch.setattr(config, "get_db", lambda: FakeConn())
    config.set_param("coef_siguranta", 0.3)
    assert saved['committed'] is True
```

Run: `python -m pytest tests/test_forecast_config.py -v`
Expected: passed.

- [ ] **Step 5: Commit**

```bash
git add app/blueprints/forecast.py app/templates/forecast_setari.html tests/test_forecast_config.py
git commit -m "feat(forecast): configurable parameters screen (spec 9)"
```

---

## Task 10: Frontend — model toggle, SUSPECT badge, seasonality gating, transparency popover

**Files:**
- Modify: `app/templates/forecast.html`

**Interfaces:**
- Consumes: `r.n_suspect` (Stoc rows, Task 8); `item.n_suspect`/`item.suspects` (Suggest items, Task 7); `model`/`compare` flags (Tasks 7–8 routes).

- [ ] **Step 1: Model toggle (mirror the existing `3ani/90zile` toggle near line 196)**

Add a link-group toggle in the Stoc-tab toolbar that flips `?model=`, preserving current query args, plus a "Comparație" link that sets `compare=1`:
```html
<div class="btn-group btn-group-sm ms-2" role="group">
  <a class="btn btn-outline-secondary {{ 'active' if model != 'nou' }}"
     href="{{ url_for('forecast.forecast', tab='stoc', brand=sel_brand, gama=sel_gama, urgenta=sel_urgenta, q=sel_search, vel=sel_vel, model='actual') }}">Model actual</a>
  <a class="btn btn-outline-secondary {{ 'active' if model == 'nou' }}"
     href="{{ url_for('forecast.forecast', tab='stoc', brand=sel_brand, gama=sel_gama, urgenta=sel_urgenta, q=sel_search, vel=sel_vel, model='nou') }}">Model nou (client × articol)</a>
</div>
```

- [ ] **Step 2: SUSPECT badge in the Stoc table**

In the row where the urgency `badge` is emitted (≈ line 293), append, guarded:
```html
{% if r.n_suspect and r.n_suspect > 0 %}
  <span class="badge bg-warning text-dark ms-1"
        title="{{ r.n_suspect }} client(i) suspecți de delistare — contribuția lor a fost exclusă din prognoză">Suspect delistare</span>
{% endif %}
```
Add the same badge cell to the Suggest table rows using `item.n_suspect`.

- [ ] **Step 3: Seasonality gating in the "Sezon" cell (Suggest tab)**

Where the per-month `idx` chips render (`months_detail`), when the article had `<24` months of history the profile carries index `1.0` for every month. Add a muted marker when all indices equal 1.0:
```html
{% set flat = item.months | map(attribute='idx') | select('equalto', 1.0) | list %}
{% if flat | length == item.months | length %}
  <span class="text-muted small" title="Fără ajustare sezonieră (&lt;24 luni istoric)">fără ajustare</span>
{% endif %}
```

- [ ] **Step 4: Suggestion transparency popover**

On the `Sug. Total` cell (Suggest tab), add a Bootstrap tooltip/`title` breakdown built from item fields already present (`demand_ro`, `demand_export`, `stoc_qty`, `in_tranzit`, and — new — safety). Add `safety_ro`/`safety_export` to the item dict in Task 7 so the popover can read them; render:
```html
<span title="Prognoză×(lead+acoperire): RO {{ item.demand_ro }} + Exp {{ item.demand_export }} · siguranță {{ (item.safety_ro + item.safety_export) | round(1) }} − stoc {{ item.stoc_qty }} − tranzit {{ item.in_tranzit }} → rotunjit la bax">{{ item.suggested }}</span>
```

- [ ] **Step 5: Compare mode columns**

When `compare` is set, the route computes both models. Simplest reliable approach: the Stoc route, when `compare=1`, builds `rows` from `model='actual'` and a parallel `rows_nou` from `model='nou'`, then zips `suggested_ro/hu` into each row as `suggested_ro_nou`/`suggested_hu_nou`. In the template, when `compare`, add two extra columns showing the new suggestion and the delta:
```html
{% if compare %}
  <td class="text-end small">{{ r.suggested_ro_nou }}</td>
  <td class="text-end small {{ 'text-danger' if (r.suggested_ro_nou or 0) < (r.suggested_ro or 0) else 'text-success' }}">
    {{ (r.suggested_ro_nou or 0) - (r.suggested_ro or 0) }}</td>
{% endif %}
```
(Implement the `compare` branch in `app/blueprints/forecast.py`: call `forecast_stoc_extended` twice and merge by `sku`; pass `compare=compare`.)

- [ ] **Step 6: Manual verification**

Start the app (`Start-Hub.bat` or `tools/Start-Hub.ps1`) → `http://localhost:5000/forecast`. Verify: (a) toggle switches model and URL carries `model=nou`; (b) a known declining/delisted SKU shows the "Suspect delistare" badge under the new model; (c) `?compare=1` shows the Δ columns; (d) `/forecast/setari` shows the Parametri forecast card and edits persist after refresh.

- [ ] **Step 7: Commit**

```bash
git add app/templates/forecast.html app/blueprints/forecast.py
git commit -m "feat(forecast): model toggle, suspect badge, seasonality gating, transparency + compare view"
```

---

## Task 11: Documentation + backlog reconciliation

**Files:**
- Modify: `app/forecast/README.md`, `context/STATUS.md`, `docs/TECHNICAL.md` (if it documents forecast config/schema), `docs/BACKLOG.md`.

- [ ] **Step 1:** Update `app/forecast/README.md` — document the `client × article` model, `pair_engine.py`, the `forecast_config` table + `/forecast/setari` params, and the `?model=nou` / `?compare=1` toggles. Note which spec items remain deferred (link `docs/decision.html` items 5–10).
- [ ] **Step 2:** Update `context/STATUS.md` "Next immediate step" — reflect that the client×article core shipped behind a toggle and is pending owner validation + decisions 5–10.
- [ ] **Step 3:** Read `docs/BACKLOG.md`; tick/remove any items now delivered (e.g. "zeros in monthly mean", "seasonality cap", "delisting signal", "safety-stock/bax rounding", "forecast config screen"). Leave blocked items, annotating them with the `docs/decision.html` reference.
- [ ] **Step 4:** Run the full suite + lint: `python -m pytest tests/ -q && ruff check .`. Expected: green.
- [ ] **Step 5: Commit**

```bash
git add app/forecast/README.md context/STATUS.md docs/TECHNICAL.md docs/BACKLOG.md
git commit -m "docs(forecast): document client-article model; reconcile backlog"
```

---

## Self-Review

**Spec coverage (in-scope items):** §2 aggregation → Task 5; §4.1 window → Task 2; §4.2 zeros → Task 2; §4.3 seasonality gate+cap → Task 3; §5.1 SUSPECT → Task 4 (+ surfaced Tasks 7–10); §8 safety/coverage/bax → Task 6 (wired 7–8); §9 config → Tasks 1, 9; §11 acceptance #3/#4 → Task 4, #6 → Task 5, #8 → Task 6, seasonal #2 → Task 3. Compare caveat → Tasks 7–10. Deferred items (§4.4, §5 lifecycle, §6, §7 guard, §8 MOQ, §10 UI) are explicitly out of scope and mapped to `docs/decision.html` 5–10.

**Placeholder scan:** each code step carries full code; UI steps give concrete markup + anchors; no TBD/TODO.

**Type consistency:** `article_monthly_profiles` returns the `{sku: {ro, export, total, cod_produs, suspects, n_active, n_suspect}}` shape consumed by Tasks 7–8; `split_with_safety` returns `suggested_ro`/`suggested_export` (matching `_ro_hu_split` keys the consumers already read) plus `safety_ro`/`safety_export` used by the Task 10 popover; `config.get_params()` keys match the params referenced in Tasks 5–8.
