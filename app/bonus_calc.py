"""Bonus calculation logic matching simulator_bonus.xlsx."""

PAYOUT_GRID = [
    (0.0,  0.0),
    (0.80, 0.5),
    (0.90, 0.8),
    (1.00, 1.0),
    (1.02, 1.1),
    (1.10, 1.2),
    (1.20, 1.5),
]

# Poarta globala pe vanzari: sub acest procent din target, niciun KPI nu se
# declanseaza, oricat de bine ar fi realizat (decizie proprietar 2026-09-22).
SALES_GATE = 0.80

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


def sales_realizare(kpis: list) -> float | None:
    """Realizarea agregată pe criteriul vânzări (None dacă nu există target).

    Dacă sunt mai multe rânduri de vânzări, se agregă Σactual / Σtarget.
    """
    target = actual = 0.0
    for k in kpis:
        if k.get("tip") == "vanzari":
            target += k.get("target") or 0.0
            actual += k.get("actual") or 0.0
    return (actual / target) if target else None


def sales_gate_blocked(kpis: list, gate: float = SALES_GATE) -> bool:
    """True dacă vânzările sunt sub poartă → niciun KPI nu se declanșează."""
    realizare = sales_realizare(kpis)
    return realizare is not None and realizare < gate


def calc_agent_month(monthly_bonus: float, penalty: float,
                     kpis: list, grid: list | None = None,
                     gate: float = SALES_GATE) -> dict:
    """Calculează bonusul lunar al unui agent din lista de rânduri KPI.

    bonus = monthly_bonus * Σ(pondere_i * multiplier_i) * (1 - penalty)

    Poartă globală: dacă realizarea pe vânzări < `gate` (80% din target),
    toți multiplicatorii devin 0 — niciun KPI nu se plătește, chiar dacă e
    îndeplinit. Poarta nu se aplică dacă nu există target de vânzări.
    """
    factor = 1.0 - (penalty or 0.0)
    blocked = sales_gate_blocked(kpis, gate)
    calc_rows = []
    scor = 0.0
    for k in kpis:
        r = calc_kpi(k, grid)
        if blocked:
            r["multiplier"] = 0.0
            r["weighted"] = 0.0
            r["blocat_gate"] = True
        r["bonus"] = round((monthly_bonus or 0.0) * r["weighted"] * factor, 2)
        scor += r["weighted"]
        calc_rows.append(r)
    scor_rounded = round(scor, 4)
    return {
        "kpis": calc_rows,
        "scor": scor_rounded,
        "total_pondere": round(sum((k.get("pondere") or 0.0) for k in kpis), 4),
        "total_bonus": round((monthly_bonus or 0.0) * scor_rounded * factor, 2),
        "gate_vanzari": blocked,
        "gate_prag": gate,
    }


