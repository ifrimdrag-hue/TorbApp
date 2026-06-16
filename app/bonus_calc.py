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

MONTHS_RO = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
             'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


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


