"""Logica de calcul preturi pentru pachete gifting si Trendyol.

Conventii:
- price_min = costul nostru / pragul minim
- price_v   = pret standard de vanzare
- price_max = pret maxim recomandat
- TVA: deja inclus in price_v (asa cum se vinde catre client)
"""



SHIPPING_TRENDYOL = 11.0  # lei, suportat de noi
PSYCHOLOGICAL_ENDINGS = [0.90, 9.90, 19.90, 29.90, 39.90, 49.90, 59.90, 69.90,
                         79.90, 89.90, 99.90, 109.90, 129.90, 149.90, 179.90,
                         199.90, 229.90, 249.90, 279.90, 299.90, 349.90, 399.90,
                         449.90, 499.90, 599.90, 699.90, 799.90, 899.90, 999.90]


# ───────── Gifting ─────────

def gifting_totals(products: list[dict]) -> dict:
    """products: lista cu {price_min, price_v, price_max, qty, ...}"""
    cost = sum((p.get("price_min") or 0) * (p.get("qty") or 1) for p in products)
    standard = sum((p.get("price_v") or 0) * (p.get("qty") or 1) for p in products)
    max_total = sum((p.get("price_max") or 0) * (p.get("qty") or 1) for p in products)
    return {
        "cost": round(cost, 2),
        "standard": round(standard, 2),
        "max": round(max_total, 2),
    }


def _round_psy(target: float) -> float:
    """Gaseste cel mai apropiat prag psihologic SUB target (sa fie 'atragator')."""
    candidates = [e for e in PSYCHOLOGICAL_ENDINGS if e <= target]
    if not candidates:
        return PSYCHOLOGICAL_ENDINGS[0]
    # extinde: dincolo de tabel, adauga 100 lei pana acoperim target
    base = max(candidates)
    # adauga si variante "+X00" sub target (ex: 1199.90)
    extras = []
    n = 1
    while base + n * 100 < target:
        extras.append(round(base + n * 100, 2))
        n += 1
    return max([base] + extras)


def _margin_pct(final: float, cost: float) -> float:
    if final <= 0:
        return 0.0
    return round((final - cost) / final * 100, 1)


def gifting_price_variants(products: list[dict]) -> dict:
    """Calculeaza cele 3 variante de pret. User va alege una sau scrie alta."""
    totals = gifting_totals(products)
    standard = totals["standard"]
    cost = totals["cost"]
    max_total = totals["max"]

    # Varianta A: discount procent (mediu 6%) din pretul standard, rotunjit .90
    discount_pct = 6.0
    a_raw = standard * (1 - discount_pct / 100)
    # rotunjeste in jos la .90 cel mai apropiat
    a_val = int(a_raw) + 0.90 if (a_raw - int(a_raw)) >= 0.90 else int(a_raw) - 0.10
    if a_val < cost:
        a_val = round(cost * 1.10, 2)  # safety: 10% peste cost minim

    variant_a = {
        "label": "Discount procent (6%)",
        "value": round(a_val, 2),
        "discount_from_standard": round(standard - a_val, 2),
        "discount_pct": discount_pct,
        "margin_pct": _margin_pct(a_val, cost),
    }

    # Varianta B: prag psihologic sub pretul standard
    psy = _round_psy(standard)
    if psy < cost:
        psy = round(cost * 1.10, 2)
    variant_b = {
        "label": "Prag psihologic",
        "value": round(psy, 2),
        "discount_from_standard": round(standard - psy, 2),
        "discount_pct": round((standard - psy) / standard * 100, 1) if standard > 0 else 0,
        "margin_pct": _margin_pct(psy, cost),
    }

    # Varianta C: doar info (user decide singur)
    variant_c = {
        "label": "Doar info (decizi tu)",
        "cost": cost,
        "standard": standard,
        "max": max_total,
        "suggested_range": [round(standard * 0.92, 2), round(standard, 2)],
        "margin_at_standard_pct": _margin_pct(standard, cost),
    }

    return {
        "totals": totals,
        "percent_off": variant_a,
        "psychological": variant_b,
        "info_only": variant_c,
    }


# ───────── Trendyol ─────────

def trendyol_suggest_qty(price_v: float) -> int:
    """Cantitate sugerata pentru bundle Trendyol (b: AI suggests)."""
    if price_v < 20:
        return 4
    if price_v < 40:
        return 4
    if price_v < 80:
        return 3
    return 3


def trendyol_calc(price_min: float, price_v: float, qty: int,
                  shipping: float = SHIPPING_TRENDYOL) -> dict:
    """Calculeaza pret bundle Trendyol cu transport inclus (suportat de noi).

    Formula:
      base = price_v * qty
      cost_real_pentru_noi = price_min * qty + shipping
      pret_sugerat = base + shipping - mic_discount (3-4%)
                   sau prag psihologic sub (base + shipping)
    """
    base = price_v * qty
    cost_real = price_min * qty + shipping
    inclusiv = base + shipping  # pret normal cu transport inclus

    # Varianta cu discount mic 3.5%
    disc_pct = 3.5
    d_val = inclusiv * (1 - disc_pct / 100)
    # rotunjire la .90
    d_val_rounded = int(d_val) + 0.90 if (d_val - int(d_val)) >= 0.90 else int(d_val) - 0.10
    if d_val_rounded < cost_real:
        d_val_rounded = round(cost_real * 1.05, 2)

    # Varianta psy
    psy = _round_psy(inclusiv)
    if psy < cost_real:
        psy = round(cost_real * 1.05, 2)

    margin_d = d_val_rounded - cost_real
    margin_psy = psy - cost_real

    return {
        "qty": qty,
        "price_v_per_buc": round(price_v, 2),
        "price_min_per_buc": round(price_min, 2),
        "shipping_cost": shipping,
        "cost_real": round(cost_real, 2),
        "standard_bundle_with_shipping": round(inclusiv, 2),
        "percent_off": {
            "label": "Discount 3.5%",
            "value": round(d_val_rounded, 2),
            "margin_total": round(margin_d, 2),
            "margin_pct": _margin_pct(d_val_rounded, cost_real),
        },
        "psychological": {
            "label": "Prag psihologic",
            "value": round(psy, 2),
            "margin_total": round(margin_psy, 2),
            "margin_pct": _margin_pct(psy, cost_real),
        },
        "info_only": {
            "cost_per_buc": round(price_min, 2),
            "cost_total": round(cost_real, 2),
            "standard_total": round(inclusiv, 2),
            "suggested_range": [round(inclusiv * 0.95, 2), round(inclusiv, 2)],
        },
    }
