"""Calculator de preturi pe campanie + estimator de reach.

Logica de aplicare a reducerii:
  - Reducerea se aplica DOAR pe Pret V (pretul actual de vanzare)
  - Pret Minim si Pret Maxim raman cum sunt din file (ele sunt floor/ceiling)
  - Pentru eMAG output: 3 preturi (min / v_nou / max)
  - Pentru Shopify output: 1 pret (v_nou)

Reach estimator:
  - Foloseste benchmark-uri CPM indicative pentru piata RO
  - User poate ajusta CPM-ul de la setari (viitor)
"""

from io import BytesIO
from typing import NamedTuple

from openpyxl import Workbook

from .._shared.prices import load_snapshot, build_lookup, normalize_match_key
from .models import Campaign


# Benchmark-uri CPM indicative — RON per 1000 impresii (Romania, 2026)
CPM_BENCHMARKS = {
    "instagram": 15.0,
    "facebook":  10.0,
}
ENGAGEMENT_RATE = 0.025  # 2.5% engagement (medie estimata)


class PriceLine(NamedTuple):
    sku: str
    codmare: str | None
    name: str
    brand: str | None
    found: bool
    base_min: float | None
    base_v: float | None
    base_max: float | None
    new_v: float | None
    new_min: float | None  # de obicei = base_min
    new_max: float | None  # de obicei = base_max
    note: str


def _apply_discount(base_v: float | None, dtype: str, dvalue: float | None) -> float | None:
    if base_v is None:
        return None
    if dtype == "none" or dvalue is None:
        return base_v
    if dtype == "percent_off":
        return round(base_v * (1 - dvalue / 100), 2)
    if dtype == "fixed_off":
        return round(max(base_v - dvalue, 0), 2)
    if dtype == "fixed_price":
        return round(dvalue, 2)
    return base_v


def calculate_prices(campaign: Campaign) -> dict:
    snapshot = load_snapshot()
    if not snapshot:
        return {
            "ok": False,
            "error": (
                "Nu exista lista de preturi salvata. Mergi la Campanii → Calendar campanii "
                "si apasa 'Incarca preturi' (sus, langa 'Stoc actualizat')."
            ),
        }

    by_ean, by_cod = build_lookup(snapshot)
    discount = campaign.discount

    lines: list[PriceLine] = []
    for p in campaign.products:
        # Match: EAN nu e direct accesibil aici (nu il avem in CampaignProduct),
        # deci match-uim pe cod_articol normalizat (codmare daca exista, fallback pe sku)
        match_key = normalize_match_key(p.codmare) or normalize_match_key(p.sku)
        rec = by_cod.get(match_key) if match_key else None

        if not rec:
            lines.append(PriceLine(
                sku=p.sku, codmare=p.codmare, name=p.name, brand=None,
                found=False,
                base_min=None, base_v=None, base_max=None,
                new_v=None, new_min=None, new_max=None,
                note="Negasit in lista de preturi",
            ))
            continue

        base_min = rec.get("price_min")
        base_v   = rec.get("price_v")
        base_max = rec.get("price_max")
        new_v    = _apply_discount(base_v, discount.type, discount.value)

        # Avertisment daca new_v ajunge sub base_min (sub pretul minim)
        note = ""
        if new_v is not None and base_min is not None and new_v < base_min:
            note = f"⚠ Sub Pret Minim ({base_min:.2f})"

        lines.append(PriceLine(
            sku=p.sku, codmare=p.codmare, name=rec.get("name") or p.name,
            brand=rec.get("brand"),
            found=True,
            base_min=base_min, base_v=base_v, base_max=base_max,
            new_v=new_v, new_min=base_min, new_max=base_max,
            note=note,
        ))

    matched = sum(1 for x in lines if x.found)
    not_found = len(lines) - matched
    warnings = sum(1 for x in lines if x.note)

    # Generam si Excel-ul de export
    excel_bytes = _build_excel(campaign, lines)

    return {
        "ok": True,
        "snapshot_uploaded_at": snapshot["uploaded_at"],
        "campaign_name": campaign.name,
        "discount_applied": discount.model_dump(),
        "summary": {
            "total_products": len(lines),
            "matched": matched,
            "not_found": not_found,
            "warnings_below_min": warnings,
        },
        "lines": [_line_to_dict(ln) for ln in lines],
        "file_b64": _b64(excel_bytes),
    }


def _line_to_dict(ln: PriceLine) -> dict:
    return {
        "sku": ln.sku,
        "codmare": ln.codmare,
        "name": ln.name,
        "brand": ln.brand,
        "found": ln.found,
        "base_min": ln.base_min,
        "base_v": ln.base_v,
        "base_max": ln.base_max,
        "new_v": ln.new_v,
        "new_min": ln.new_min,
        "new_max": ln.new_max,
        "note": ln.note,
    }


def _b64(data: bytes) -> str:
    import base64
    return base64.b64encode(data).decode("ascii")


def _build_excel(campaign: Campaign, lines: list[PriceLine]) -> bytes:
    wb = Workbook()
    # Sheet 1: eMAG (3 preturi)
    ws_emag = wb.active
    ws_emag.title = "eMAG"
    ws_emag.append([
        "SKU (cod articol)", "Denumire", "Brand",
        "Pret Minim (NEW)", "Pret V (NEW)", "Pret Maxim (NEW)",
        "Pret Minim (OLD)", "Pret V (OLD)", "Pret Maxim (OLD)",
        "Note",
    ])
    for ln in lines:
        ws_emag.append([
            ln.codmare or ln.sku, ln.name, ln.brand or "",
            ln.new_min, ln.new_v, ln.new_max,
            ln.base_min, ln.base_v, ln.base_max,
            ln.note,
        ])

    # Sheet 2: Shopify (1 pret)
    ws_shop = wb.create_sheet("Shopify")
    ws_shop.append(["SKU", "Denumire", "Brand", "Pret nou", "Pret vechi", "Note"])
    for ln in lines:
        ws_shop.append([
            ln.codmare or ln.sku, ln.name, ln.brand or "",
            ln.new_v, ln.base_v, ln.note,
        ])

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def estimate_reach(campaign: Campaign, override_cpm: dict | None = None) -> dict:
    """Estimeaza reach-ul pe baza bugetului si canalelor de comunicare alese."""
    if not campaign.budget_alloc or campaign.budget_alloc <= 0:
        return {
            "ok": False,
            "error": "Nu ai setat un buget alocat pentru campanie.",
        }

    posting_channels = [c for c in campaign.channels if c in ("instagram", "facebook")]
    if not posting_channels:
        return {
            "ok": False,
            "error": "Selecteaza cel putin un canal de comunicare (Instagram sau Facebook) ca sa estimam reach-ul.",
        }

    cpm = {**CPM_BENCHMARKS, **(override_cpm or {})}
    total_budget = float(campaign.budget_alloc)
    # Distributie egala pe canale (se poate rafina ulterior)
    per_channel_budget = total_budget / len(posting_channels)

    breakdown = []
    total_reach = 0
    total_engagement = 0
    for ch in posting_channels:
        ch_cpm = cpm.get(ch, 12.0)
        impressions = (per_channel_budget / ch_cpm) * 1000 if ch_cpm > 0 else 0
        engagement = impressions * ENGAGEMENT_RATE
        breakdown.append({
            "channel": ch,
            "budget": round(per_channel_budget, 2),
            "cpm": ch_cpm,
            "estimated_impressions": int(impressions),
            "estimated_engaged": int(engagement),
        })
        total_reach += impressions
        total_engagement += engagement

    return {
        "ok": True,
        "campaign_name": campaign.name,
        "total_budget": total_budget,
        "breakdown": breakdown,
        "total_estimated_impressions": int(total_reach),
        "total_estimated_engaged": int(total_engagement),
        "engagement_rate_assumed": ENGAGEMENT_RATE,
        "note": (
            "Estimari indicative bazate pe benchmark-uri medii din piata RO. "
            "Reach-ul real depinde de targeting, calitatea creative-ului, sezon, competitie. "
            "Cand vei avea date din primele tale campanii, putem ajusta CPM-urile la valorile tale reale."
        ),
    }
