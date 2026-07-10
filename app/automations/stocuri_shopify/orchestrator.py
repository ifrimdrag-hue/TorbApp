"""Orchestrator pentru sincronizare stoc Shopify (mod API direct).

Flow:
  1. preview()  — parseaza raportul intern + preia inventarul live din Shopify
                   → returneaza tabel comparativ (stoc vechi vs nou) pentru review
  2. sync()     — trimite actualizarile de stoc prin inventorySetQuantities mutation
                   → returneaza rezultate per-produs
"""

from collections import defaultdict
from typing import NamedTuple

from config import settings
from .._shared.report_parser import parse_excel
from .._shared.snapshot import save_snapshot
from .csv_filler import _normalize_sku as _norm
from .api_client import ShopifyClient


class ShopifyPreviewRow(NamedTuple):
    inventory_item_id: str
    sku: str
    name: str
    old_stock: int
    new_stock: int | None
    status: str  # updated | zeroed_threshold | unchanged | no_sku | no_report
    matched_by: str | None = None  # sku | ean | None


class ShopifyPreviewResult(NamedTuple):
    rows: list[ShopifyPreviewRow]
    skus_not_in_shopify: list[dict]
    warnings: list[str]
    summary: dict
    has_report: bool = True


class ShopifySyncResult(NamedTuple):
    results: list[dict]
    success_count: int
    error_count: int


async def preview(report_bytes: bytes, source_filename: str = "") -> ShopifyPreviewResult:
    parsed = parse_excel(report_bytes)
    save_snapshot(parsed, source_filename)
    threshold = settings.shopify_stock_safety_threshold

    # Primary match: codmare vs Shopify variant SKU. Fallback: report EAN vs
    # variant barcode — survives ERP codmare renumbering (2026-07-10 incident).
    raw_by_sku: dict[str, int] = defaultdict(int)
    raw_by_ean: dict[str, int] = defaultdict(int)
    cms_of_ean: dict[str, set[str]] = defaultdict(set)
    skus_unmatchable: list[dict] = []
    for row in parsed.rows:
        cm = _norm(row.codmare) if row.codmare else None
        if cm:
            raw_by_sku[cm] += row.qty
        if row.ean:
            raw_by_ean[row.ean] += row.qty
            if cm:
                cms_of_ean[row.ean].add(cm)
        if not cm and not row.ean:
            skus_unmatchable.append({"sku": row.sku, "qty": row.qty})

    client = ShopifyClient()
    live_items = await client.fetch_all_inventory()

    all_shopify_skus = {n for n in (_norm(item["sku"]) for item in live_items) if n}
    rows: list[ShopifyPreviewRow] = []
    matched_eans: set[str] = set()

    for item in live_items:
        n = _norm(item["sku"])
        barcode = (item.get("barcode") or "").strip()
        old = item["on_hand"]

        if n and n in raw_by_sku:
            real, matched_by = raw_by_sku[n], "sku"
        elif barcode and barcode in raw_by_ean:
            real, matched_by = raw_by_ean[barcode], "ean"
            matched_eans.add(barcode)
        else:
            real, matched_by = None, None

        if real is not None:
            new = 0 if real <= threshold else real
            if real <= threshold:
                status = "zeroed_threshold" if new != old else "unchanged"
            else:
                status = "updated" if new != old else "unchanged"
            rows.append(ShopifyPreviewRow(
                inventory_item_id=item["inventory_item_id"], sku=item["sku"],
                name=item["name"], old_stock=old, new_stock=new, status=status,
                matched_by=matched_by,
            ))
        elif not n:
            rows.append(ShopifyPreviewRow(
                inventory_item_id=item["inventory_item_id"], sku=item["sku"],
                name=item["name"], old_stock=old, new_stock=None, status="no_sku",
            ))
        else:
            rows.append(ShopifyPreviewRow(
                inventory_item_id=item["inventory_item_id"], sku=item["sku"],
                name=item["name"], old_stock=old, new_stock=None, status="unchanged",
            ))

    cms_matched_via_ean: set[str] = set()
    for ean in matched_eans:
        cms_matched_via_ean |= cms_of_ean[ean]

    skus_not_in_shopify = [
        {"codmare": cm, "qty": raw_by_sku[cm]}
        for cm in raw_by_sku
        if cm not in all_shopify_skus and cm not in cms_matched_via_ean
    ]

    warnings = list(parsed.warnings)
    if skus_unmatchable:
        warnings.append(f"{len(skus_unmatchable)} SKU-uri din raport fara codmare si fara EAN (sarite)")

    summary = {
        "total_shopify_items": len(rows),
        "to_update": sum(1 for r in rows if r.status in ("updated", "zeroed_threshold")),
        "updated_with_stock": sum(1 for r in rows if r.status == "updated"),
        "zeroed_threshold": sum(1 for r in rows if r.status == "zeroed_threshold"),
        "unchanged": sum(1 for r in rows if r.status == "unchanged"),
        "no_sku": sum(1 for r in rows if r.status == "no_sku"),
        "matched_by_ean": sum(1 for r in rows if r.matched_by == "ean"),
        "not_in_shopify": len(skus_not_in_shopify),
        "safety_threshold": threshold,
        "report_warnings": len(parsed.warnings),
    }

    return ShopifyPreviewResult(
        rows=rows, skus_not_in_shopify=skus_not_in_shopify,
        warnings=warnings, summary=summary,
    )


async def sync(rows_to_update: list[dict]) -> ShopifySyncResult:
    updates = [
        {
            "inventory_item_id": r["inventory_item_id"],
            "sku": r.get("sku", ""),
            "name": r.get("name", ""),
            "new_stock": r["new_stock"],
        }
        for r in rows_to_update
    ]
    client = ShopifyClient()
    raw = await client.set_on_hand_quantities(updates)

    results = [
        {
            "inventory_item_id": r["inventory_item_id"],
            "sku": r.get("sku", ""),
            "name": r.get("name", ""),
            "new_stock": r.get("new_stock"),
            "ok": r["ok"],
            "error": r.get("error"),
        }
        for r in raw
    ]
    success_count = sum(1 for r in results if r["ok"])
    error_count = len(results) - success_count
    return ShopifySyncResult(results=results, success_count=success_count, error_count=error_count)


async def preview_shopify_only() -> ShopifyPreviewResult:
    client = ShopifyClient()
    live_items = await client.fetch_all_inventory()

    rows = [
        ShopifyPreviewRow(
            inventory_item_id=item["inventory_item_id"], sku=item["sku"],
            name=item["name"], old_stock=item["on_hand"], new_stock=None,
            status="no_sku" if not _norm(item["sku"]) else "no_report",
        )
        for item in live_items
    ]
    summary = {
        "total_shopify_items": len(rows),
        "no_sku": sum(1 for r in rows if r.status == "no_sku"),
    }
    return ShopifyPreviewResult(
        rows=rows, skus_not_in_shopify=[], warnings=[], summary=summary, has_report=False,
    )
