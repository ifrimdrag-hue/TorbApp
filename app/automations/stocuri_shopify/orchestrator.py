"""Orchestrator pentru sincronizare stoc Shopify (mod Inventory CSV).

Flow:
  1. parseaza raportul intern (acelasi parser ca pentru eMAG)
  2. agregare cantitate pe codmare (NU pe cod — pentru ca codmare e cheia care
     se potriveste cu Variant SKU pe Shopify)
  3. aplica pragul de siguranta (stoc <= prag → 0)
  4. completeaza CSV-ul Shopify Inventory cu valorile corecte in 'On hand (new)'
"""

from collections import defaultdict
from typing import NamedTuple

from config import settings
from .._shared.report_parser import parse_excel
from .._shared.snapshot import save_snapshot
from .csv_filler import fill_inventory_csv, _normalize_sku as _norm


class StockSyncResult(NamedTuple):
    file_bytes: bytes
    summary: dict
    warnings: list[str]
    skus_no_codmare: list[dict]            # SKU-uri din raport fara codmare (sarite)
    codmare_not_in_shopify: list[str]      # codmare din raport care nu apar in Shopify
    codmare_below_threshold: list[dict]    # codmare cu stoc <= prag (zerificate)


def run(report_bytes: bytes, csv_bytes: bytes, source_filename: str = "") -> StockSyncResult:
    parsed = parse_excel(report_bytes)
    save_snapshot(parsed, source_filename)
    threshold = settings.emag_stock_safety_threshold  # acelasi prag ca eMAG

    # Agregare pe codmare normalizat (aceeasi normalizare ca SKU-urile Shopify
    # — strip apostrof + strip sufix -XX — pentru match simetric)
    raw_stocks_by_codmare: dict[str, int] = defaultdict(int)
    skus_no_codmare: list[dict] = []
    for r in parsed.rows:
        cm_norm = _norm(r.codmare) if r.codmare else None
        if cm_norm:
            raw_stocks_by_codmare[cm_norm] += r.qty
        else:
            skus_no_codmare.append({"sku": r.sku, "qty": r.qty})

    # Aplicam pragul de siguranta
    stocks_by_codmare: dict[str, int] = {}
    codmare_below_threshold: list[dict] = []
    for cm, qty in raw_stocks_by_codmare.items():
        if qty <= threshold:
            stocks_by_codmare[cm] = 0
            codmare_below_threshold.append({"codmare": cm, "qty_real": qty})
        else:
            stocks_by_codmare[cm] = qty

    fill = fill_inventory_csv(csv_bytes, stocks_by_codmare)

    codmare_not_in_shopify = sorted(set(raw_stocks_by_codmare.keys()) - fill.matched_skus)

    # Defalcare matched: cu stoc real vs zerificate prin prag
    below_set = {x["codmare"] for x in codmare_below_threshold}
    shopify_active = len(fill.matched_skus - below_set)
    shopify_zero_low_stock = len(fill.matched_skus & below_set)

    summary = {
        "report_total_rows": parsed.total_rows_in_file,
        "report_unique_skus": len(parsed.rows),
        "report_duplicates_summed": parsed.duplicates_summed,
        "report_skus_with_codmare": len(raw_stocks_by_codmare),
        "report_skus_no_codmare": len(skus_no_codmare),
        # Stare finala pe Shopify (Shop location)
        "shopify_active": shopify_active,
        "shopify_zero_low_stock": shopify_zero_low_stock,
        "shopify_zero_not_in_report": fill.set_to_zero,
        "shopify_rows_other_location": fill.rows_other_location,
        # Pierderi
        "codmare_not_in_shopify": len(codmare_not_in_shopify),
        "safety_threshold": threshold,
        "codmare_below_threshold_total": len(codmare_below_threshold),
    }

    return StockSyncResult(
        file_bytes=fill.file_bytes,
        summary=summary,
        warnings=parsed.warnings,
        skus_no_codmare=skus_no_codmare,
        codmare_not_in_shopify=codmare_not_in_shopify,
        codmare_below_threshold=codmare_below_threshold,
    )
