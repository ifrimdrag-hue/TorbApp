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

    raw_by_sku: dict[str, int] = defaultdict(int)
    skus_no_codmare: list[dict] = []
    for row in parsed.rows:
        cm = _norm(row.codmare) if row.codmare else None
        if cm:
            raw_by_sku[cm] += row.qty
        else:
            skus_no_codmare.append({"sku": row.sku, "qty": row.qty})

    new_by_sku: dict[str, int] = {
        cm: (0 if qty <= threshold else qty) for cm, qty in raw_by_sku.items()
    }

    client = ShopifyClient()
    live_items = await client.fetch_all_inventory()

    shopify_by_sku: dict[str, dict] = {}
    for item in live_items:
        n = _norm(item["sku"])
        if n:
            shopify_by_sku[n] = item

    all_shopify_skus = set(shopify_by_sku.keys())
    rows: list[ShopifyPreviewRow] = []

    for item in live_items:
        n = _norm(item["sku"])
        old = item["on_hand"]

        if not n:
            rows.append(ShopifyPreviewRow(
                inventory_item_id=item["inventory_item_id"], sku=item["sku"],
                name=item["name"], old_stock=old, new_stock=None, status="no_sku",
            ))
            continue

        if n in new_by_sku:
            new = new_by_sku[n]
            real = raw_by_sku[n]
            if real <= threshold:
                status = "zeroed_threshold" if new != old else "unchanged"
            else:
                status = "updated" if new != old else "unchanged"
            rows.append(ShopifyPreviewRow(
                inventory_item_id=item["inventory_item_id"], sku=item["sku"],
                name=item["name"], old_stock=old, new_stock=new, status=status,
            ))
        else:
            rows.append(ShopifyPreviewRow(
                inventory_item_id=item["inventory_item_id"], sku=item["sku"],
                name=item["name"], old_stock=old, new_stock=None, status="unchanged",
            ))

    skus_not_in_shopify = [
        {"codmare": cm, "qty": raw_by_sku[cm]}
        for cm in raw_by_sku
        if cm not in all_shopify_skus
    ]

    warnings = list(parsed.warnings)
    if skus_no_codmare:
        warnings.append(f"{len(skus_no_codmare)} SKU-uri din raport fara codmare (sarite)")

    summary = {
        "total_shopify_items": len(rows),
        "to_update": sum(1 for r in rows if r.status in ("updated", "zeroed_threshold")),
        "updated_with_stock": sum(1 for r in rows if r.status == "updated"),
        "zeroed_threshold": sum(1 for r in rows if r.status == "zeroed_threshold"),
        "unchanged": sum(1 for r in rows if r.status == "unchanged"),
        "no_sku": sum(1 for r in rows if r.status == "no_sku"),
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
