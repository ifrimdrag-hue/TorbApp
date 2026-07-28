"""Shopify preview matching: codmare primary, EAN fallback (codmare renumbering)."""
import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest


def _report_bytes(rows):
    df = pd.DataFrame(rows, columns=["cod", "codmare", "codbare", "cantit"])
    buf = BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


REPORT = _report_bytes([
    # matches Shopify SKU 70177-00 only via EAN (ERP renumbered codmare)
    ("1032", "70173-00", "4792252002098", 48),
    # matches Shopify SKU 70855 directly by codmare
    ("1044", "70855-00", "111", 100),
    # below safety threshold -> zeroed
    ("222", "70430-00", "222", 3),
    # in report but nowhere on Shopify
    ("999", "88888-00", "333", 60),
    # no codmare and no EAN -> unmatchable warning
    ("777", None, None, 10),
])

SHOPIFY_ITEMS = [
    {"inventory_item_id": "gid://1", "sku": "70177-00", "barcode": "4792252002098",
     "name": "Earl Grey 25 bags", "on_hand": 10},
    {"inventory_item_id": "gid://2", "sku": "70855", "barcode": "",
     "name": "Frosty Afternoon", "on_hand": 100},
    {"inventory_item_id": "gid://3", "sku": "70430-00", "barcode": "222",
     "name": "Refill Frosty", "on_hand": 8},
    {"inventory_item_id": "gid://4", "sku": "", "barcode": "",
     "name": "No identifiers", "on_hand": 5},
    {"inventory_item_id": "gid://5", "sku": "50000-00", "barcode": "444",
     "name": "Not in report", "on_hand": 7},
]


@pytest.fixture
def preview_result(monkeypatch):
    from automations.stocuri_shopify import orchestrator
    from config import settings

    monkeypatch.setattr(settings, "shopify_stock_safety_threshold", 5)
    monkeypatch.setattr(orchestrator, "save_snapshot", lambda *a, **k: None)

    with patch.object(orchestrator, "ShopifyClient") as MockClient:
        MockClient.return_value.fetch_all_inventory = AsyncMock(return_value=SHOPIFY_ITEMS)
        return asyncio.run(orchestrator.preview(REPORT, "stoc test.xlsx"))


def _row(result, iid):
    return next(r for r in result.rows if r.inventory_item_id == iid)


def test_ean_fallback_matches_renumbered_codmare(preview_result):
    row = _row(preview_result, "gid://1")
    assert row.matched_by == "ean"
    assert row.status == "updated"
    assert row.new_stock == 48


def test_codmare_match_still_primary(preview_result):
    row = _row(preview_result, "gid://2")
    assert row.matched_by == "sku"
    assert row.status == "unchanged"
    assert row.new_stock == 100


def test_threshold_zeroes_low_stock(preview_result):
    row = _row(preview_result, "gid://3")
    assert row.status == "zeroed_threshold"
    assert row.new_stock == 0


def test_item_without_identifiers_is_no_sku(preview_result):
    assert _row(preview_result, "gid://4").status == "no_sku"


def test_unmatched_item_left_unchanged(preview_result):
    row = _row(preview_result, "gid://5")
    assert row.status == "unchanged"
    assert row.new_stock is None


def test_ean_matched_codmare_not_reported_missing(preview_result):
    missing = {d["codmare"] for d in preview_result.skus_not_in_shopify}
    assert "70173" not in missing          # covered via EAN fallback
    assert missing == {"88888"}


def test_summary_and_warnings(preview_result):
    assert preview_result.summary["matched_by_ean"] == 1
    assert any("fara codmare si fara EAN" in w for w in preview_result.warnings)
