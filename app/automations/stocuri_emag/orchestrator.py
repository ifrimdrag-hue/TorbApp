"""Orchestrator for eMAG stock synchronisation (API-based).

Flow:
  1. preview()  — parse internal report + fetch live eMAG offers
                   → returns a comparison table (old vs new stock) for user review
  2. sync()     — push stock updates to eMAG via bulk offer/save API
                   → returns per-offer success/error results
"""

from collections import defaultdict
from typing import NamedTuple

from config import settings
from .._shared.report_parser import parse_excel
from .._shared.snapshot import save_snapshot
from .api_client import EmagClient


class PreviewRow(NamedTuple):
    offer_id: int
    name: str
    ean: str | None
    old_stock: int
    new_stock: int | None  # None = not in report, will not be updated
    status: str            # updated | zeroed_threshold | unchanged | no_ean


class PreviewResult(NamedTuple):
    rows: list[PreviewRow]
    skus_not_in_emag: list[dict]
    warnings: list[str]
    summary: dict
    has_report: bool = True


class SyncResult(NamedTuple):
    results: list[dict]
    success_count: int
    error_count: int


def _normalize_eans(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    return [str(e).strip() for e in raw if str(e).strip()]


def _parse_stock(raw) -> int:
    """eMAG returns stock either as int or as list[{warehouse_id, value}]."""
    if isinstance(raw, list):
        return sum(s.get("value", 0) for s in raw if isinstance(s, dict))
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


async def preview(report_bytes: bytes, source_filename: str = "") -> PreviewResult:
    """Parse internal report, fetch live eMAG offers, return comparison table."""
    parsed = parse_excel(report_bytes)
    save_snapshot(parsed, source_filename)
    threshold = settings.emag_stock_safety_threshold

    # Build EAN → real qty from internal report (sum duplicate SKUs)
    raw_qty_by_ean: dict[str, int] = defaultdict(int)
    for row in parsed.rows:
        if row.ean:
            raw_qty_by_ean[row.ean] += row.qty

    # Apply safety threshold: stock <= threshold is sent as 0
    new_stock_by_ean: dict[str, int] = {
        ean: (0 if qty <= threshold else qty)
        for ean, qty in raw_qty_by_ean.items()
    }

    # Fetch all live offers from eMAG
    client = EmagClient()
    all_offers = await client.fetch_all_offers_raw()

    # Collect all eMAG EANs for "not found" detection
    all_emag_eans: set[str] = set()
    for offer in all_offers:
        all_emag_eans.update(_normalize_eans(offer.get("ean")))

    # Build comparison rows (one per eMAG offer)
    rows: list[PreviewRow] = []
    matched_eans: set[str] = set()

    for offer in all_offers:
        offer_id = offer.get("id")
        name = (offer.get("name") or offer.get("part_number") or "—").strip()
        old_stock = _parse_stock(offer.get("stock"))
        eans = _normalize_eans(offer.get("ean"))

        if not eans:
            rows.append(PreviewRow(
                offer_id=offer_id, name=name, ean=None,
                old_stock=old_stock, new_stock=None, status="no_ean",
            ))
            continue

        matched_ean = next((e for e in eans if e in new_stock_by_ean), None)
        display_ean = eans[0]

        if matched_ean:
            matched_eans.add(matched_ean)
            new_stock = new_stock_by_ean[matched_ean]
            real_qty = raw_qty_by_ean[matched_ean]
            status = "zeroed_threshold" if real_qty <= threshold else "updated"
            rows.append(PreviewRow(
                offer_id=offer_id, name=name, ean=matched_ean,
                old_stock=old_stock, new_stock=new_stock, status=status,
            ))
        else:
            rows.append(PreviewRow(
                offer_id=offer_id, name=name, ean=display_ean,
                old_stock=old_stock, new_stock=None, status="unchanged",
            ))

    # SKUs from internal report whose EAN doesn't exist on eMAG at all
    skus_not_in_emag = [
        {"sku": row.sku, "ean": row.ean, "qty": row.qty}
        for row in parsed.rows
        if row.ean and row.ean not in all_emag_eans
    ]

    summary = {
        "total_emag_offers": len(rows),
        "to_update": sum(1 for r in rows if r.status in ("updated", "zeroed_threshold")),
        "updated_with_stock": sum(1 for r in rows if r.status == "updated"),
        "zeroed_threshold": sum(1 for r in rows if r.status == "zeroed_threshold"),
        "unchanged": sum(1 for r in rows if r.status == "unchanged"),
        "no_ean": sum(1 for r in rows if r.status == "no_ean"),
        "not_in_emag": len(skus_not_in_emag),
        "safety_threshold": threshold,
        "report_warnings": len(parsed.warnings),
    }

    return PreviewResult(
        rows=rows,
        skus_not_in_emag=skus_not_in_emag,
        warnings=parsed.warnings,
        summary=summary,
    )


async def sync(rows_to_update: list[dict]) -> SyncResult:
    """Push stock updates to eMAG using bulk offer/save.

    Args:
        rows_to_update: list of {offer_id, ean, name, new_stock}
    """
    updates = [{"id": r["offer_id"], "stock": r["new_stock"]} for r in rows_to_update]

    client = EmagClient()
    raw_results = await client.bulk_update_stock(updates)

    id_to_row = {r["offer_id"]: r for r in rows_to_update}
    results = []
    for raw in raw_results:
        offer_id = raw["id"]
        row = id_to_row.get(offer_id, {})
        results.append({
            "offer_id": offer_id,
            "ean": row.get("ean", ""),
            "name": row.get("name", ""),
            "new_stock": row.get("new_stock"),
            "ok": raw["ok"],
            "error": raw.get("error"),
        })

    success_count = sum(1 for r in results if r["ok"])
    error_count = sum(1 for r in results if not r["ok"])

    return SyncResult(results=results, success_count=success_count, error_count=error_count)


async def preview_emag_only() -> PreviewResult:
    """Fetch live eMAG offers without an internal report.

    All rows get new_stock=None and status='no_report' (or 'no_ean' if offer
    has no EAN). No snapshot is saved since there is no report data.
    """
    client = EmagClient()
    all_offers = await client.fetch_all_offers_raw()

    rows: list[PreviewRow] = []
    for offer in all_offers:
        offer_id = offer.get("id")
        name = (offer.get("name") or offer.get("part_number") or "—").strip()
        old_stock = _parse_stock(offer.get("stock"))
        eans = _normalize_eans(offer.get("ean"))
        ean = eans[0] if eans else None
        rows.append(PreviewRow(
            offer_id=offer_id,
            name=name,
            ean=ean,
            old_stock=old_stock,
            new_stock=None,
            status="no_ean" if ean is None else "no_report",
        ))

    summary = {
        "total_emag_offers": len(rows),
        "no_ean": sum(1 for r in rows if r.ean is None),
    }

    return PreviewResult(
        rows=rows,
        skus_not_in_emag=[],
        warnings=[],
        summary=summary,
        has_report=False,
    )
