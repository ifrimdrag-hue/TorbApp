"""Client x article forecast core (spec §2, §4, §5).

Pure functions operate on in-memory month->qty dicts so they are unit
testable; article_monthly_profiles() adds the DB fetch + aggregation.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from db import query


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


def delisting_status(purchase_dates, today, min_days, mult, confirm_days=0):
    """Adaptive delisting status (spec §5.1–5.2).

    ACTIV → SUSPECT once days-since-last > max(min_days, mult × mean interval).
    A SUSPECT pair auto-confirms to DELISTAT after a further `confirm_days`
    (spec §5.2, `confirmare_delistare_zile`) with no purchase. SUSPECT and
    DELISTAT both contribute 0 to the article forecast — the label only feeds
    reporting. `confirm_days=0` (default) disables the DELISTAT transition so
    existing callers keep the old two-state behaviour.
    """
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
    if days_since_last > prag:
        status = "SUSPECT"
        if confirm_days and days_since_last > prag + float(confirm_days):
            status = "DELISTAT"
    else:
        status = "ACTIV"
    return {"status": status, "days_since_last": days_since_last,
            "mean_interval": mean_interval, "prag": prag}


def _last_closed_months(today, n):
    """The `n` closed months ending at the month before `today`."""
    y, m = _month_add(today.year, today.month, -1)
    out = []
    for _ in range(int(n)):
        out.append((y, m))
        y, m = _month_add(y, m, -1)
    return out


def neutral_months(client_month_qty, window, threshold_pct, min_clients=2):
    """Level-1 neutral-month heuristic (Brief §4.1).

    A month in `window` is NEUTRAL when at least `threshold_pct`% of the clients
    whose active span (first…last sale month) covers it sold zero that month —
    a signal about supply/offer, not per-client churn. Requires ≥ `min_clients`
    covering clients so a single client cannot trip it. Neutral months are
    excluded from the pair means. Returns a set of (year, month).
    `client_month_qty`: {client: {(y, m): qty}}.
    """
    if not window:
        return set()
    spans = {}
    for c, months in client_month_qty.items():
        if months:
            keys = sorted(months.keys())
            spans[c] = (keys[0], keys[-1])
    thr = threshold_pct / 100.0
    out = set()
    for ym in window:
        covering = [c for c, (lo, hi) in spans.items() if lo <= ym <= hi]
        if len(covering) < min_clients:
            continue
        zeros = sum(1 for c in covering if client_month_qty[c].get(ym, 0.0) <= 0)
        if zeros / len(covering) >= thr:
            out.add(ym)
    return out


def is_inactive(article_month_qty, today, months, seasonal_idx=None,
                neutral=None, seasonal_cap=3.0):
    """Global 6-month cut (spec §7): zero total sales across the last `months`
    closed months → INACTIV (article forecast 0). Neutral months (supply gaps)
    don't count as evidence of no demand; strongly seasonal articles (peak
    seasonal index ≥ `seasonal_cap`) are never auto-inactivated by this flat
    rule (spec §7, seasonal exception).
    """
    if seasonal_idx and max(seasonal_idx.values(), default=1.0) >= seasonal_cap:
        return False
    neutral = neutral or set()
    recent = [ym for ym in _last_closed_months(today, months) if ym not in neutral]
    if not recent:
        return False
    return sum(article_month_qty.get(ym, 0.0) for ym in recent) <= 0


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
    out = []
    for r in query(sql, {"f": furnizor, "cutoff": cutoff_year}):
        try:
            y, m, dd = (int(x) for x in str(r["data_dl"])[:10].split("-"))
            d = date(y, m, dd)
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

    confirm_days = params.get("confirmare_delistare_zile", 0)
    neutru_pct = params.get("prag_neutru_multi_client", 100.0)
    inactiv_luni = params.get("taiere_inactiv_luni", 6)

    result = {}
    for sku, clients in grp.items():
        s_idx = seasonal_index(
            art_month_qty[sku], params["sezonalitate_min_luni"],
            params["indice_sezonier_min"], params["indice_sezonier_max"])

        # Article-wide neutral months (Brief §4.1) from per-client monthly qty.
        cmq = {}
        for c, markets in clients.items():
            agg = defaultdict(float)
            for mm in markets.values():
                for ym, q in mm.items():
                    agg[ym] += q
            cmq[c] = dict(agg)
        art_win = build_window(min(first_sale[sku].values()), today, window_months)
        neutral = neutral_months(cmq, art_win, neutru_pct)

        base = {"ro": 0.0, "export": 0.0}
        suspects, n_active = [], 0
        for c, markets in clients.items():
            ds = delisting_status(pdates[sku][c], today,
                                  params["prag_delistare_zile"],
                                  params["prag_delistare_mult"], confirm_days)
            if ds["status"] in ("SUSPECT", "DELISTAT"):
                suspects.append({"cod_client": c, "client": name_of[(sku, c)],
                                 "days_since_last": ds["days_since_last"],
                                 "mean_interval": ds["mean_interval"],
                                 "status": ds["status"]})
                continue
            n_active += 1
            win = [ym for ym in build_window(first_sale[sku][c], today,
                                             window_months) if ym not in neutral]
            for mkt in ("ro", "export"):
                if mkt in markets:
                    base[mkt] += monthly_mean_with_zeros(markets[mkt], win)

        inactive = is_inactive(art_month_qty[sku], today, inactiv_luni,
                               s_idx, neutral)
        if inactive:
            base = {"ro": 0.0, "export": 0.0}
        ro = {m: base["ro"] * s_idx[m] for m in range(1, 13)}
        exp = {m: base["export"] * s_idx[m] for m in range(1, 13)}
        result[sku] = {
            "ro": ro, "export": exp,
            "total": {m: ro[m] + exp[m] for m in range(1, 13)},
            "cod_produs": cod_of.get(sku),
            "suspects": suspects, "n_active": n_active,
            "n_suspect": len(suspects),
            "n_delistat": sum(1 for s in suspects if s.get("status") == "DELISTAT"),
            "inactive": inactive,
            "neutral_months": sorted(neutral),
        }
    return result
