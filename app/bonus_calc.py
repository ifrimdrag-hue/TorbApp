"""Bonus calculation logic matching simulator_bonus.xlsx."""

PAYOUT_GRID = [
    (0.0,  0.0),
    (0.80, 0.5),
    (0.95, 0.8),
    (1.00, 1.0),
    (1.02, 1.1),
    (1.10, 1.2),
    (1.20, 1.5),
]

PRESETS = {
    "Claudiu": {
        "db_agent": "BRINZA CLAUDIU",
        "monthly_bonus": 4000,
        "growth_pct": 0.20,
        "w_sales": 0.45,
        "w_margin": 0.25,
        "w_strategic": 0.30,
        "gate_sales": 0.80,
        "gate_margin": 0.80,
        "penalty": 0.0,
    },
    "Bogdan": {
        "db_agent": "DRAGNEA BOGDAN",
        "monthly_bonus": 4000,
        "growth_pct": 0.20,
        "w_sales": 0.50,
        "w_margin": 0.25,
        "w_strategic": 0.25,
        "gate_sales": 0.80,
        "gate_margin": 0.80,
        "penalty": 0.0,
    },
    "Oana": {
        "db_agent": "Oana Filip",
        "monthly_bonus": 3000,
        "growth_pct": 0.20,
        "w_sales": 0.50,
        "w_margin": 0.20,
        "w_strategic": 0.30,
        "gate_sales": 0.80,
        "gate_margin": 0.80,
        "penalty": 0.0,
    },
    "Ionut": {
        "db_agent": "CONSTANTIN IONUT",
        "monthly_bonus": 2000,
        "growth_pct": 0.20,
        "w_sales": 0.50,
        "w_margin": 0.20,
        "w_strategic": 0.30,
        "gate_sales": 0.80,
        "gate_margin": 0.80,
        "penalty": 0.0,
    },
    "Teo": {
        "db_agent": None,
        "monthly_bonus": 500,
        "growth_pct": 0.20,
        "w_sales": 0.45,
        "w_margin": 0.25,
        "w_strategic": 0.30,
        "gate_sales": 0.80,
        "gate_margin": 0.80,
        "penalty": 0.0,
    },
}

MONTHS_RO = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
             'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# January–December (all 12 months)
SIM_MONTHS = list(range(1, 13))

STRATEGIC_BRANDS = ['Basilur', 'Delaviuda', 'Leonex', 'Celmar', 'Toras']

# Default weights for strategic brands (sum = 1.0)
STRATEGIC_WEIGHTS_DEFAULT = {
    'Basilur':   0.30,
    'Toras':     0.25,
    'Leonex':    0.20,
    'Celmar':    0.15,
    'Delaviuda': 0.10,
}


def payout_multiplier(score: float, grid: list | None = None) -> float:
    g = grid if grid is not None else PAYOUT_GRID
    result = g[0][1]
    for threshold, multiplier in g:
        if score >= threshold:
            result = multiplier
        else:
            break
    return result


def calc_kpi(kpi: dict, grid: list | None = None) -> dict:
    """Calculează realizarea și multiplicatorul pentru un singur rând KPI.

    kpi: {tip, target, actual, pondere}
    Returnează kpi-ul augmentat cu realizare, multiplier, weighted.
    """
    target = kpi.get("target") or 0.0
    actual = kpi.get("actual") or 0.0
    pondere = kpi.get("pondere") or 0.0
    realizare = (actual / target) if target else 0.0
    multiplier = payout_multiplier(realizare, grid)
    weighted = pondere * multiplier
    return {
        **kpi,
        "realizare": round(realizare, 4),
        "multiplier": multiplier,
        "weighted": round(weighted, 4),
    }


def calc_agent_month(monthly_bonus: float, penalty: float,
                     kpis: list, grid: list | None = None) -> dict:
    """Calculează bonusul lunar al unui agent din lista de rânduri KPI.

    bonus = monthly_bonus * Σ(pondere_i * multiplier_i) * (1 - penalty)
    """
    factor = 1.0 - (penalty or 0.0)
    calc_rows = []
    scor = 0.0
    for k in kpis:
        r = calc_kpi(k, grid)
        r["bonus"] = round((monthly_bonus or 0.0) * r["weighted"] * factor, 2)
        scor += r["weighted"]
        calc_rows.append(r)
    scor_rounded = round(scor, 4)
    return {
        "kpis": calc_rows,
        "scor": scor_rounded,
        "total_pondere": round(sum((k.get("pondere") or 0.0) for k in kpis), 4),
        "total_bonus": round((monthly_bonus or 0.0) * scor_rounded * factor, 2),
    }


def calc_month(params: dict, month_data: dict) -> dict:
    """Calculate bonus for a single month.

    params keys: monthly_bonus, w_sales, w_margin, w_strategic,
                 gate_sales, gate_margin, penalty, growth_pct
    month_data keys: base_sales, actual_sales, base_margin, actual_margin,
                     strategic_att, collection_factor
    """
    mb = params["monthly_bonus"]
    w_s = params["w_sales"]
    w_m = params["w_margin"]
    w_st = params["w_strategic"]
    gate_s = params["gate_sales"]
    gate_m = params["gate_margin"]
    penalty = params["penalty"]
    growth = params["growth_pct"]

    base_s = month_data.get("base_sales") or 0
    base_m = month_data.get("base_margin") or 0
    actual_s = month_data.get("actual_sales") or 0
    actual_m = month_data.get("actual_margin") or 0
    strategic_att = month_data.get("strategic_att") or 0.0
    coll = month_data.get("collection_factor") or 1.0

    target_s = base_s * (1 + growth)
    target_m = base_m * (1 + growth)

    sales_att = (actual_s / target_s) if target_s else 0.0
    margin_att = (actual_m / target_m) if target_m else 0.0

    sales_mult = payout_multiplier(sales_att)
    margin_mult = payout_multiplier(margin_att)
    strategic_mult = payout_multiplier(strategic_att)

    factor = coll * (1 - penalty)

    gates_ok = sales_att >= gate_s and margin_att >= gate_m
    sales_bonus = mb * w_s * sales_mult * factor if mb and sales_att >= gate_s else 0.0
    margin_bonus = mb * w_m * margin_mult * factor if mb and margin_att >= gate_m else 0.0
    strategic_bonus = mb * w_st * strategic_mult * factor if mb and gates_ok else 0.0

    return {
        "target_sales": round(target_s, 0),
        "target_margin": round(target_m, 0),
        "sales_att": round(sales_att, 4),
        "margin_att": round(margin_att, 4),
        "strategic_att": round(strategic_att, 4),
        "sales_mult": sales_mult,
        "margin_mult": margin_mult,
        "strategic_mult": strategic_mult,
        "gate_sales_ok": sales_att >= gate_s,
        "gate_margin_ok": margin_att >= gate_m,
        "gate_strategic_ok": gates_ok,
        "sales_bonus": round(sales_bonus, 2),
        "margin_bonus": round(margin_bonus, 2),
        "strategic_bonus": round(strategic_bonus, 2),
        "total_bonus": round(sales_bonus + margin_bonus + strategic_bonus, 2),
    }


def simulate(params: dict, months_data: list) -> dict:
    """Run full simulation for all months."""
    results = []
    for i, md in enumerate(months_data):
        r = calc_month(params, md)
        r["month"] = SIM_MONTHS[i] if i < len(SIM_MONTHS) else i + 4
        r["month_label"] = MONTHS_RO[r["month"] - 1]
        results.append(r)

    annual_bonus = sum(r["total_bonus"] for r in results)
    annual_target = params["monthly_bonus"] * len(results)

    return {
        "months": results,
        "annual_bonus": round(annual_bonus, 2),
        "annual_target": annual_target,
        "payout_pct": round(annual_bonus / annual_target * 100, 1) if annual_target else 0,
    }
