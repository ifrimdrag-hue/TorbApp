# Shopify API Stock Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual CSV export/import Shopify workflow with a live API-based sync identical in UX to the existing eMAG page — upload internal report → fetch live Shopify inventory → review comparison table → push changes directly via API.

**Architecture:** A new `api_client.py` uses the Shopify Admin GraphQL API to fetch product variants and inventory levels and push bulk stock updates in a single mutation call. The existing `orchestrator.py` gets `preview()` / `sync()` functions alongside the unchanged `run()` CSV function. The Shopify page gains an "API mode" tab while keeping the CSV tab as fallback.

**Tech Stack:** Shopify Admin GraphQL API 2025-01, `gql[httpx]` (async GraphQL client), Flask async routes, Bootstrap tabs, vanilla JS mirroring `stocuri-emag.js`.

**Key advantage over REST:** The `inventorySetQuantities` GraphQL mutation updates all items in batches of 100 in a single API call — vs one HTTP call per variant with REST. For 300 variants: 3 GraphQL calls instead of 300 REST calls.

---

## Shopify API Credentials — What You Must Do First

Before any code runs, you need to create a Shopify Custom App and obtain credentials. These steps are done entirely in the Shopify Admin dashboard and require no code changes.

### Step 1 — Enable custom app development

1. Go to your Shopify Admin → **Settings** → **Apps and sales channels**
2. Click **Develop apps** (top right)
3. If prompted, click **Allow custom app development** and confirm

### Step 2 — Create the app

1. Click **Create an app**
2. Name it `Torb Stock Sync`, leave developer as yourself
3. Click **Create app**

### Step 3 — Configure API scopes

1. Inside the new app, click **Configure Admin API scopes**
2. Enable exactly these four scopes:
   - `read_products`
   - `read_inventory`
   - `write_inventory`
   - `read_locations`
3. Click **Save**

### Step 4 — Install and copy the token

1. Click **Install app** → confirm
2. Under **Admin API access token**, click **Reveal token once**
3. **Copy the full token now** — it starts with `shpat_` and is shown only this one time
4. Open `.env` and set:
   ```
   SHOPIFY_ACCESS_TOKEN=shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

### Step 5 — Find your Location ID

After Task 3 is implemented, call the connection-test endpoint:
```
GET http://localhost:5000/api/stocuri/shopify/connection-test
```
The response includes a `locations` array. Find your main warehouse location and copy its numeric `id` (not the full `gid://` string — just the number at the end).

Then set in `.env`:
```
SHOPIFY_LOCATION_ID=12345678
```

Restart the server after each `.env` change.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | **Modify** | Add `gql[httpx]>=3.5` |
| `app/automations/stocuri_shopify/request_logger.py` | **Create** | Rotating JSON log for Shopify API calls → `logs/shopify_req.json` |
| `app/automations/stocuri_shopify/api_client.py` | **Create** | Shopify GraphQL: connection test, fetch variants+inventory, bulk set inventory |
| `app/automations/stocuri_shopify/orchestrator.py` | **Modify** | Add `PreviewRow`, `preview()`, `preview_shopify_only()`, `sync()` alongside existing `run()` |
| `app/blueprints/stocuri_shopify.py` | **Modify** | Add routes: `connection-test`, `preview`, `sync` |
| `app/templates/stocuri/shopify.html` | **Modify** | Add tab switcher: "Mod API" (new) + "Mod CSV" (existing) |
| `app/static/js/stocuri-shopify.js` | **Modify** | Add full API mode: connection dot, preview table with pagination, sync |

---

## Task 1 — Add `gql[httpx]` dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Add `gql[httpx]` to requirements.txt**

Add this line after `httpx>=0.28`:
```
gql[httpx]>=3.5
```

- [ ] **Install the dependency**

```
.venv\Scripts\pip install gql[httpx]
```

Expected output ends with `Successfully installed gql-...` and `httpx-...` (already present).

- [ ] **Commit**
```
git add requirements.txt
git commit -m "feat: add gql[httpx] dependency for Shopify GraphQL client"
```

---

## Task 2 — `request_logger.py`

**Files:**
- Create: `app/automations/stocuri_shopify/request_logger.py`

Identical pattern to `app/automations/stocuri_emag/request_logger.py` but writes to `logs/shopify_req.json`. With GraphQL, `payload` will contain the query name and variables; `response` will contain the parsed result dict.

- [ ] **Create the file**

```python
"""Rotating JSON log for Shopify API requests — keeps the last MAX_ENTRIES records."""

import json
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

_LOG_FILE = Path(__file__).resolve().parents[3] / "logs" / "shopify_req.json"
MAX_ENTRIES = 20


def _read() -> list:
    try:
        return json.loads(_LOG_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write(entries: list) -> None:
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _LOG_FILE.write_text(
        json.dumps(entries[-MAX_ENTRIES:], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _parse_body(text: str):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def append(
    *,
    url: str,
    payload,
    status_code: int | None = None,
    response_text: str | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
) -> None:
    response = _parse_body(response_text) if response_text is not None else None
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "url": url,
        "payload": payload,
        "status_code": status_code,
        "response": response,
        "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
        "error": error,
    }
    entries = _read()
    entries.append(entry)
    _write(entries)


@contextmanager
def capture(*, url: str, payload):
    """Context manager that times the block and appends the result automatically."""
    class _Ctx:
        status_code: int | None = None
        response_text: str | None = None

    ctx = _Ctx()
    t0 = time.perf_counter()
    try:
        yield ctx
    except Exception as exc:
        append(
            url=url,
            payload=payload,
            status_code=ctx.status_code,
            response_text=ctx.response_text,
            duration_ms=(time.perf_counter() - t0) * 1000,
            error=str(exc),
        )
        raise
    else:
        append(
            url=url,
            payload=payload,
            status_code=ctx.status_code,
            response_text=ctx.response_text,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
```

- [ ] **Commit**
```
git add app/automations/stocuri_shopify/request_logger.py
git commit -m "feat: add Shopify request logger (rotating 20-entry JSON log)"
```

---

## Task 3 — `api_client.py`

**Files:**
- Create: `app/automations/stocuri_shopify/api_client.py`

Uses `gql[httpx]` with `HTTPXAsyncTransport` for async GraphQL calls against the Shopify Admin API.

**GraphQL endpoint:** `POST https://{shop_domain}/admin/api/{version}/graphql.json`

**Authentication:** `X-Shopify-Access-Token` header.

**IDs:** Shopify GraphQL returns Global IDs (GIDs) like `gid://shopify/InventoryItem/12345678`. These are strings and are passed directly back in mutations — no conversion needed. The user stores only the numeric portion of the Location GID in `.env`; the client constructs the full GID internally.

**Batching:** `inventorySetQuantities` accepts up to 100 quantities per call. `bulk_set_inventory` splits into batches of 100 automatically.

**Rate limiting:** Shopify GraphQL uses cost-based throttling (1000 points/sec refill). Each query costs ~1–2 points; the mutation with 100 items costs ~100 points. For typical sync operations this stays well within limits.

- [ ] **Create the file**

```python
"""Shopify Admin GraphQL API client for inventory sync."""

import logging
from gql import gql, Client
from gql.transport.httpx import HTTPXAsyncTransport

from config import settings
from . import request_logger

log = logging.getLogger(__name__)

BATCH_SIZE = 100  # max quantities per inventorySetQuantities call

# ── GraphQL documents (parsed once at import time) ────────────────────────────

_Q_SHOP = gql("""
query ShopInfo {
  shop {
    name
    myshopifyDomain
  }
}
""")

_Q_LOCATIONS = gql("""
query Locations {
  locations(first: 50, includeInactive: false) {
    edges {
      node {
        id
        name
        isActive
      }
    }
  }
}
""")

_Q_VARIANTS = gql("""
query ProductVariants($cursor: String) {
  productVariants(first: 250, after: $cursor) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        sku
        displayName
        inventoryItem {
          id
        }
      }
    }
  }
}
""")

_Q_INVENTORY = gql("""
query InventoryLevels($locationId: ID!, $cursor: String) {
  location(id: $locationId) {
    inventoryLevels(first: 250, after: $cursor) {
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        node {
          item {
            id
          }
          quantities(names: ["available"]) {
            name
            quantity
          }
        }
      }
    }
  }
}
""")

_M_SET_INVENTORY = gql("""
mutation SetInventory($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) {
    inventoryAdjustmentGroup {
      changes {
        item { id }
        quantityAfterChange
      }
    }
    userErrors {
      field
      message
    }
  }
}
""")


class ShopifyClient:
    def __init__(self):
        if not settings.shopify_shop_domain or not settings.shopify_access_token:
            raise RuntimeError(
                "Shopify API not configured. Set SHOPIFY_SHOP_DOMAIN and "
                "SHOPIFY_ACCESS_TOKEN in .env"
            )
        domain = settings.shopify_shop_domain.strip().rstrip("/")
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        version = settings.shopify_api_version or "2025-01"
        self._url = f"{domain}/admin/api/{version}/graphql.json"
        self._headers = {"X-Shopify-Access-Token": settings.shopify_access_token}

    def _check_location(self) -> None:
        if not settings.shopify_location_id:
            raise RuntimeError(
                "SHOPIFY_LOCATION_ID not set in .env. "
                "Call /api/stocuri/shopify/connection-test to find your location ID."
            )

    @property
    def _location_gid(self) -> str:
        return f"gid://shopify/Location/{settings.shopify_location_id}"

    def _client(self) -> Client:
        transport = HTTPXAsyncTransport(url=self._url, headers=self._headers)
        return Client(transport=transport, fetch_schema_from_transport=False)

    async def test_connection(self) -> dict:
        """Verify credentials and return shop info + available locations."""
        async with self._client() as session:
            with request_logger.capture(
                url=self._url, payload={"query": "ShopInfo"}
            ) as ctx:
                shop_result = await session.execute(_Q_SHOP)
                ctx.status_code = 200
                ctx.response_text = str(shop_result)

            with request_logger.capture(
                url=self._url, payload={"query": "Locations"}
            ) as ctx:
                loc_result = await session.execute(_Q_LOCATIONS)
                ctx.status_code = 200
                ctx.response_text = str(loc_result)

        shop = shop_result.get("shop", {})
        locations = [
            {
                "id": edge["node"]["id"].split("/")[-1],  # numeric part for .env
                "gid": edge["node"]["id"],
                "name": edge["node"]["name"],
                "active": edge["node"]["isActive"],
            }
            for edge in loc_result.get("locations", {}).get("edges", [])
        ]
        return {
            "shop_name": shop.get("name"),
            "shop_domain": shop.get("myshopifyDomain"),
            "locations": locations,
        }

    async def fetch_all_variants_raw(self) -> list[dict]:
        """Fetch all product variants with SKU and inventory item GID.

        Returns list of:
          {variant_id (GID str), sku, inventory_item_id (GID str), name}
        where name = displayName ("Product Title / Variant Title").
        """
        variants: list[dict] = []
        cursor = None

        async with self._client() as session:
            while True:
                variables = {"cursor": cursor} if cursor else {}
                with request_logger.capture(
                    url=self._url,
                    payload={"query": "ProductVariants", "cursor": cursor},
                ) as ctx:
                    result = await session.execute(_Q_VARIANTS, variable_values=variables)
                    ctx.status_code = 200
                    ctx.response_text = str(result)

                pv = result["productVariants"]
                for edge in pv["edges"]:
                    node = edge["node"]
                    variants.append({
                        "variant_id": node["id"],
                        "sku": node.get("sku") or "",
                        "inventory_item_id": node["inventoryItem"]["id"],
                        "name": node.get("displayName") or "",
                    })

                page_info = pv["pageInfo"]
                if not page_info["hasNextPage"]:
                    break
                cursor = page_info["endCursor"]

        return variants

    async def fetch_inventory_levels_raw(self) -> list[dict]:
        """Fetch all inventory levels at the configured location.

        Returns list of:
          {inventory_item_id (GID str), available (int)}
        """
        self._check_location()
        levels: list[dict] = []
        cursor = None
        location_gid = self._location_gid

        async with self._client() as session:
            while True:
                variables: dict = {"locationId": location_gid}
                if cursor:
                    variables["cursor"] = cursor

                with request_logger.capture(
                    url=self._url,
                    payload={"query": "InventoryLevels", "locationId": location_gid, "cursor": cursor},
                ) as ctx:
                    result = await session.execute(_Q_INVENTORY, variable_values=variables)
                    ctx.status_code = 200
                    ctx.response_text = str(result)

                location_data = result.get("location")
                if not location_data:
                    raise RuntimeError(
                        f"Location {location_gid} not found. "
                        "Check SHOPIFY_LOCATION_ID in .env."
                    )

                inv = location_data.get("inventoryLevels", {})
                for edge in inv.get("edges", []):
                    node = edge["node"]
                    available = next(
                        (q["quantity"] for q in node.get("quantities", [])
                         if q["name"] == "available"),
                        0,
                    )
                    levels.append({
                        "inventory_item_id": node["item"]["id"],
                        "available": available or 0,
                    })

                page_info = inv.get("pageInfo", {})
                if not page_info.get("hasNextPage"):
                    break
                cursor = page_info.get("endCursor")

        return levels

    async def bulk_set_inventory(self, updates: list[dict]) -> list[dict]:
        """Set inventory for multiple items via inventorySetQuantities mutation.

        Sends batches of up to BATCH_SIZE items per mutation call.

        Args:
            updates: list of {inventory_item_id (GID str), name, sku, new_stock}

        Returns:
            list of {inventory_item_id, name, sku, new_stock, ok, error}
        """
        self._check_location()
        location_gid = self._location_gid
        results: list[dict] = []

        async with self._client() as session:
            for i in range(0, len(updates), BATCH_SIZE):
                batch = updates[i : i + BATCH_SIZE]
                variables = {
                    "input": {
                        "name": "available",
                        "reason": "correction",
                        "quantities": [
                            {
                                "inventoryItemId": item["inventory_item_id"],
                                "locationId": location_gid,
                                "quantity": item["new_stock"],
                            }
                            for item in batch
                        ],
                    }
                }
                try:
                    with request_logger.capture(
                        url=self._url,
                        payload={"mutation": "SetInventory", "batch_size": len(batch)},
                    ) as ctx:
                        result = await session.execute(
                            _M_SET_INVENTORY, variable_values=variables
                        )
                        ctx.status_code = 200
                        ctx.response_text = str(result)

                    user_errors = (
                        result.get("inventorySetQuantities", {}).get("userErrors") or []
                    )
                    if user_errors:
                        error_msg = "; ".join(
                            f"{e['field']}: {e['message']}" for e in user_errors
                        )
                        for item in batch:
                            results.append({**item, "ok": False, "error": error_msg})
                    else:
                        for item in batch:
                            results.append({**item, "ok": True, "error": None})

                except Exception as exc:
                    for item in batch:
                        results.append({**item, "ok": False, "error": str(exc)})

        return results
```

- [ ] **Commit**
```
git add app/automations/stocuri_shopify/api_client.py
git commit -m "feat: add Shopify GraphQL API client (gql[httpx], bulk inventory mutation)"
```

---

## Task 4 — Update `orchestrator.py`

**Files:**
- Modify: `app/automations/stocuri_shopify/orchestrator.py`

Add `PreviewRow`, `PreviewResult`, `SyncResult`, `preview()`, `preview_shopify_only()`, and `sync()` above the existing content.

**Important:** All IDs (`variant_id`, `inventory_item_id`) are **strings** (Shopify GIDs like `gid://shopify/InventoryItem/12345`) — not integers as in the eMAG implementation.

SKU matching reuses `_norm` (already imported from `csv_filler.py`), applied symmetrically to both the Shopify `variant.sku` and the report `codmare`.

- [ ] **Replace the full file content**

```python
"""Orchestrator pentru sincronizare stoc Shopify.

Two modes:
  API mode (new):
    1. preview()              — parse internal report + fetch live Shopify inventory
                                → comparison table (old vs new stock) for user review
    2. sync()                 — push selected stock updates via Shopify GraphQL API
    3. preview_shopify_only() — fetch inventory without internal report

  CSV mode (original):
    run()                     — produce updated Shopify Inventory CSV for manual import
"""

from collections import defaultdict
from typing import NamedTuple

from config import settings
from .._shared.report_parser import parse_excel
from .._shared.snapshot import save_snapshot
from .csv_filler import fill_inventory_csv, _normalize_sku as _norm
from .api_client import ShopifyClient


# ─── API mode ────────────────────────────────────────────────────────────────

class PreviewRow(NamedTuple):
    variant_id: str           # GID: gid://shopify/ProductVariant/...
    inventory_item_id: str    # GID: gid://shopify/InventoryItem/...
    sku: str | None
    name: str                 # "Product Title / Variant Title"
    old_stock: int
    new_stock: int | None     # None = not in report, will not be updated
    status: str               # updated | zeroed_threshold | unchanged | no_sku


class PreviewResult(NamedTuple):
    rows: list[PreviewRow]
    skus_not_in_shopify: list[dict]
    warnings: list[str]
    summary: dict
    has_report: bool = True


class SyncResult(NamedTuple):
    results: list[dict]
    success_count: int
    error_count: int


async def preview(report_bytes: bytes, source_filename: str = "") -> PreviewResult:
    """Parse internal report, fetch live Shopify inventory, return comparison table."""
    parsed = parse_excel(report_bytes)
    save_snapshot(parsed, source_filename)
    threshold = settings.emag_stock_safety_threshold

    # Build normalized codmare → qty from report (sum duplicates)
    raw_qty_by_sku: dict[str, int] = defaultdict(int)
    for row in parsed.rows:
        key = _norm(row.codmare) if row.codmare else None
        if key:
            raw_qty_by_sku[key] += row.qty

    # Apply safety threshold
    new_stock_by_sku: dict[str, int] = {
        sku: (0 if qty <= threshold else qty)
        for sku, qty in raw_qty_by_sku.items()
    }

    # Fetch live Shopify data
    client = ShopifyClient()
    variants_raw = await client.fetch_all_variants_raw()
    levels_raw = await client.fetch_inventory_levels_raw()

    # Build inventory_item_id GID → available map
    stock_by_iid: dict[str, int] = {
        lvl["inventory_item_id"]: lvl["available"]
        for lvl in levels_raw
    }

    # Collect all Shopify normalized SKUs for "not found" detection
    all_shopify_skus: set[str] = set()
    for v in variants_raw:
        nsku = _norm(v["sku"]) if v["sku"] else None
        if nsku:
            all_shopify_skus.add(nsku)

    rows: list[PreviewRow] = []
    matched_skus: set[str] = set()

    for v in variants_raw:
        nsku = _norm(v["sku"]) if v["sku"] else None
        old_stock = stock_by_iid.get(v["inventory_item_id"], 0)

        if not nsku:
            rows.append(PreviewRow(
                variant_id=v["variant_id"],
                inventory_item_id=v["inventory_item_id"],
                sku=v["sku"] or None,
                name=v["name"],
                old_stock=old_stock,
                new_stock=None,
                status="no_sku",
            ))
            continue

        if nsku in new_stock_by_sku:
            matched_skus.add(nsku)
            new_stock = new_stock_by_sku[nsku]
            real_qty = raw_qty_by_sku[nsku]
            status = "zeroed_threshold" if real_qty <= threshold else "updated"
            rows.append(PreviewRow(
                variant_id=v["variant_id"],
                inventory_item_id=v["inventory_item_id"],
                sku=nsku,
                name=v["name"],
                old_stock=old_stock,
                new_stock=new_stock,
                status=status,
            ))
        else:
            rows.append(PreviewRow(
                variant_id=v["variant_id"],
                inventory_item_id=v["inventory_item_id"],
                sku=nsku,
                name=v["name"],
                old_stock=old_stock,
                new_stock=None,
                status="unchanged",
            ))

    skus_not_in_shopify = [
        {"sku": row.codmare, "qty": row.qty}
        for row in parsed.rows
        if _norm(row.codmare) and _norm(row.codmare) not in all_shopify_skus
    ]

    summary = {
        "total_shopify_variants": len(rows),
        "to_update": sum(1 for r in rows if r.status in ("updated", "zeroed_threshold")),
        "updated_with_stock": sum(1 for r in rows if r.status == "updated"),
        "zeroed_threshold": sum(1 for r in rows if r.status == "zeroed_threshold"),
        "unchanged": sum(1 for r in rows if r.status == "unchanged"),
        "no_sku": sum(1 for r in rows if r.status == "no_sku"),
        "not_in_shopify": len(skus_not_in_shopify),
        "safety_threshold": threshold,
    }

    return PreviewResult(
        rows=rows,
        skus_not_in_shopify=skus_not_in_shopify,
        warnings=parsed.warnings,
        summary=summary,
    )


async def preview_shopify_only() -> PreviewResult:
    """Fetch live Shopify inventory without an internal report."""
    client = ShopifyClient()
    variants_raw = await client.fetch_all_variants_raw()
    levels_raw = await client.fetch_inventory_levels_raw()

    stock_by_iid: dict[str, int] = {
        lvl["inventory_item_id"]: lvl["available"]
        for lvl in levels_raw
    }

    rows: list[PreviewRow] = []
    for v in variants_raw:
        nsku = _norm(v["sku"]) if v["sku"] else None
        old_stock = stock_by_iid.get(v["inventory_item_id"], 0)
        rows.append(PreviewRow(
            variant_id=v["variant_id"],
            inventory_item_id=v["inventory_item_id"],
            sku=nsku,
            name=v["name"],
            old_stock=old_stock,
            new_stock=None,
            status="no_sku" if not nsku else "no_report",
        ))

    summary = {
        "total_shopify_variants": len(rows),
        "no_sku": sum(1 for r in rows if r.sku is None),
    }

    return PreviewResult(
        rows=rows,
        skus_not_in_shopify=[],
        warnings=[],
        summary=summary,
        has_report=False,
    )


async def sync(rows_to_update: list[dict]) -> SyncResult:
    """Push stock updates to Shopify via inventorySetQuantities GraphQL mutation.

    Args:
        rows_to_update: list of {inventory_item_id (GID str), sku, name, new_stock}
    """
    client = ShopifyClient()
    raw_results = await client.bulk_set_inventory(rows_to_update)

    success_count = sum(1 for r in raw_results if r["ok"])
    error_count = sum(1 for r in raw_results if not r["ok"])

    return SyncResult(
        results=raw_results,
        success_count=success_count,
        error_count=error_count,
    )


# ─── CSV mode (unchanged) ─────────────────────────────────────────────────────

class StockSyncResult(NamedTuple):
    file_bytes: bytes
    summary: dict
    warnings: list[str]
    skus_no_codmare: list[dict]
    codmare_not_in_shopify: list[str]
    codmare_below_threshold: list[dict]


def run(report_bytes: bytes, csv_bytes: bytes, source_filename: str = "") -> StockSyncResult:
    parsed = parse_excel(report_bytes)
    save_snapshot(parsed, source_filename)
    threshold = settings.emag_stock_safety_threshold

    raw_stocks_by_codmare: dict[str, int] = defaultdict(int)
    skus_no_codmare: list[dict] = []
    for r in parsed.rows:
        cm_norm = _norm(r.codmare) if r.codmare else None
        if cm_norm:
            raw_stocks_by_codmare[cm_norm] += r.qty
        else:
            skus_no_codmare.append({"sku": r.sku, "qty": r.qty})

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

    below_set = {x["codmare"] for x in codmare_below_threshold}
    shopify_active = len(fill.matched_skus - below_set)
    shopify_zero_low_stock = len(fill.matched_skus & below_set)

    summary = {
        "report_total_rows": parsed.total_rows_in_file,
        "report_unique_skus": len(parsed.rows),
        "report_duplicates_summed": parsed.duplicates_summed,
        "report_skus_with_codmare": len(raw_stocks_by_codmare),
        "report_skus_no_codmare": len(skus_no_codmare),
        "shopify_active": shopify_active,
        "shopify_zero_low_stock": shopify_zero_low_stock,
        "shopify_zero_not_in_report": fill.set_to_zero,
        "shopify_rows_other_location": fill.rows_other_location,
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
```

- [ ] **Commit**
```
git add app/automations/stocuri_shopify/orchestrator.py
git commit -m "feat: add Shopify GraphQL preview/sync to orchestrator (keeps CSV run())"
```

---

## Task 5 — Update Blueprint

**Files:**
- Modify: `app/blueprints/stocuri_shopify.py`

Add three new async routes alongside the existing `api_shopify_run`.

- [ ] **Replace the full file content**

```python
import base64
import logging
from flask import Blueprint, render_template, request, jsonify
from automations.stocuri_shopify.orchestrator import run, preview, preview_shopify_only, sync

stocuri_shopify_bp = Blueprint('stocuri_shopify', __name__)
logger = logging.getLogger(__name__)


@stocuri_shopify_bp.route('/stocuri/shopify')
def stocuri_shopify_page():
    return render_template('stocuri/shopify.html')


# ─── CSV mode ─────────────────────────────────────────────────────────────────

@stocuri_shopify_bp.route('/api/stocuri/shopify/run', methods=['POST'])
def api_shopify_run():
    raport = request.files.get('raport')
    inventory = request.files.get('inventory')
    if not raport or not inventory:
        return jsonify({'error': 'Fisierele raport si inventory sunt obligatorii.'}), 400
    try:
        result = run(raport.read(), inventory.read(), raport.filename)
        return jsonify({
            'file_b64': base64.b64encode(result.file_bytes).decode(),
            'filename': 'inventory_updated.csv',
            'summary': result.summary,
            'warnings': result.warnings,
            'skus_no_codmare': result.skus_no_codmare,
            'codmare_not_in_shopify': result.codmare_not_in_shopify,
            'codmare_below_threshold': result.codmare_below_threshold,
        })
    except Exception as exc:
        logger.exception("Shopify CSV run failed")
        return jsonify({'error': str(exc)}), 500


# ─── API mode ─────────────────────────────────────────────────────────────────

@stocuri_shopify_bp.route('/api/stocuri/shopify/connection-test')
async def api_shopify_connection_test():
    try:
        from automations.stocuri_shopify.api_client import ShopifyClient
        client = ShopifyClient()
        info = await client.test_connection()
        return jsonify({'ok': True, **info})
    except Exception as exc:
        logger.exception("Shopify connection test failed")
        return jsonify({'ok': False, 'error': str(exc)})


@stocuri_shopify_bp.route('/api/stocuri/shopify/preview', methods=['POST'])
async def api_shopify_preview():
    raport = request.files.get('raport')
    try:
        if raport:
            result = await preview(raport.read(), raport.filename)
        else:
            result = await preview_shopify_only()
        return jsonify({
            'rows': [r._asdict() for r in result.rows],
            'skus_not_in_shopify': result.skus_not_in_shopify,
            'warnings': result.warnings,
            'summary': result.summary,
            'has_report': result.has_report,
        })
    except Exception as exc:
        logger.exception("Shopify API preview failed")
        return jsonify({'error': str(exc)}), 500


@stocuri_shopify_bp.route('/api/stocuri/shopify/sync', methods=['POST'])
async def api_shopify_sync():
    data = request.get_json(force=True)
    rows_to_update = data.get('rows_to_update', [])
    try:
        result = await sync(rows_to_update)
        return jsonify({
            'results': result.results,
            'success_count': result.success_count,
            'error_count': result.error_count,
        })
    except Exception as exc:
        logger.exception("Shopify API sync failed")
        return jsonify({'error': str(exc)}), 500
```

- [ ] **Commit**
```
git add app/blueprints/stocuri_shopify.py
git commit -m "feat: add Shopify API routes (connection-test, preview, sync)"
```

---

## Task 6 — Update Template

**Files:**
- Modify: `app/templates/stocuri/shopify.html`

Replace the entire file. Two Bootstrap tabs: **Mod API** (default) and **Mod CSV** (existing). The API tab mirrors `emag.html` exactly in structure.

- [ ] **Replace the full file**

```html
{% extends "base.html" %}
{% block title %}Stoc Shopify{% endblock %}
{% block content %}
<div class="container-fluid px-4 py-3">
  <div class="d-flex align-items-center gap-2 mb-1">
    <h4 class="mb-0">Sincronizare stoc — Shopify</h4>
    <span id="shopConnDot" class="conn-dot conn-dot--loading" title="Verific conexiunea..."></span>
  </div>

  <ul class="nav nav-tabs mb-4" id="shopTabs">
    <li class="nav-item">
      <button class="nav-link active" data-tab="api">Mod API</button>
    </li>
    <li class="nav-item">
      <button class="nav-link" data-tab="csv">Mod CSV</button>
    </li>
  </ul>

  <!-- ═══ API MODE ═══ -->
  <div id="tabApi">
    <p class="text-secondary small mb-4">
      Incarca raportul intern de stocuri. Aplicatia preia variantele live din Shopify si iti arata
      diferentele. Bifezi ce vrei sa actualizezi si apesi Sincronizeaza — stocurile se trimit direct prin API.
    </p>

    <div class="mb-3">
      <div class="dz-card p-3 border rounded" style="max-width:480px;">
        <div class="fw-semibold mb-1">Raport intern stocuri</div>
        <div class="text-secondary small mb-2">.xls / .xlsx — match dupa coloana <code>codmare</code></div>
        <div class="dropzone" id="dzShopApiReport">
          <input type="file" id="fileShopApiReport" accept=".xls,.xlsx" hidden />
          <div class="dz-inner text-center py-3">
            <strong>Trage fisierul aici</strong><br>
            <span class="text-secondary small">sau click pentru a alege</span><br>
            <small id="nameShopApiReport" class="text-info"></small>
          </div>
        </div>
      </div>
    </div>

    <div class="d-flex gap-2 mb-3">
      <button id="btnShopApiPreview" class="btn btn-primary">Incarca stoc Shopify</button>
      <button id="btnShopApiSync" class="btn btn-success" disabled>Sincronizeaza pe Shopify</button>
    </div>

    <div id="shopApiStatus" class="status mb-2"></div>

    <div id="shopApiPreviewSection" hidden>
      <div id="shopApiSummary" class="mb-3"></div>
      <div id="shopApiIssues" class="issues"></div>

      <div class="emag-toolbar mb-2" id="shopApiToolbar" hidden>
        <label class="emag-filter-label me-2">Filtreaza:</label>
        <select id="shopApiFilter" class="form-select form-select-sm d-inline-block w-auto">
          <option value="">Toate</option>
          <option value="updated">De actualizat</option>
          <option value="zeroed_threshold">Zerificate</option>
          <option value="unchanged">Nemodificate</option>
          <option value="no_sku">Fara SKU</option>
        </select>
      </div>

      <div class="emag-table-wrap table-responsive">
        <table class="emag-table table table-sm table-hover" id="shopApiTable">
          <thead>
            <tr>
              <th style="width:36px;"><input type="checkbox" id="shopApiSelectAll" title="Selecteaza tot" /></th>
              <th data-sort="name" style="cursor:pointer;">Produs / Varianta</th>
              <th data-sort="sku" style="cursor:pointer;">SKU</th>
              <th style="text-align:right; cursor:pointer;" data-sort="old_stock">Stoc Shopify</th>
              <th style="text-align:right; cursor:pointer;" data-sort="new_stock">Stoc nou</th>
              <th data-sort="status" style="cursor:pointer;">Status</th>
            </tr>
          </thead>
          <tbody id="shopApiTableBody"></tbody>
        </table>
      </div>

      <div class="emag-pagination d-flex align-items-center gap-2 my-2">
        <button id="shopApiPrevPage" class="btn btn-sm btn-outline-secondary" disabled>← Anterior</button>
        <span id="shopApiPaginationInfo" class="emag-pagination-info text-secondary small"></span>
        <button id="shopApiNextPage" class="btn btn-sm btn-outline-secondary" disabled>Urmator →</button>
      </div>
    </div>

    <div id="shopApiSyncResults" hidden>
      <div class="summary mb-2" id="shopApiSyncSummary"></div>
      <div id="shopApiSyncErrors" class="issues"></div>
    </div>
  </div>

  <!-- ═══ CSV MODE ═══ -->
  <div id="tabCsv" hidden>
    <p class="text-secondary small mb-4">
      Incarca raportul intern si CSV-ul de Inventory exportat din Shopify
      (Products → Inventory → Export → "Plain CSV file").
      Aplicatia produce un CSV cu coloana <code>On hand (new)</code> completata,
      gata de reuploadat pe Shopify (Products → Inventory → Import).
    </p>

    <div class="d-flex flex-wrap gap-3 mb-3">
      <div class="dz-card p-3 border rounded" style="max-width:360px;">
        <div class="fw-semibold small text-secondary mb-1">Pas 1</div>
        <div class="fw-semibold mb-1">Raport intern stocuri</div>
        <div class="text-secondary small mb-2">.xls / .xlsx — match dupa coloana <code>codmare</code></div>
        <div class="dropzone" id="dzShopReport">
          <input type="file" id="fileShopReport" accept=".xls,.xlsx" hidden />
          <div class="dz-inner text-center py-3">
            <strong>Trage fisierul aici</strong><br>
            <span class="text-secondary small">sau click pentru a alege</span><br>
            <small id="nameShopReport" class="text-info"></small>
          </div>
        </div>
      </div>

      <div class="dz-card p-3 border rounded" style="max-width:360px;">
        <div class="fw-semibold small text-secondary mb-1">Pas 2</div>
        <div class="fw-semibold mb-1">Shopify Inventory CSV</div>
        <div class="text-secondary small mb-2">.csv exportat din Shopify (Plain CSV, NU "for Excel")</div>
        <div class="dropzone" id="dzShopInventory">
          <input type="file" id="fileShopInventory" accept=".csv" hidden />
          <div class="dz-inner text-center py-3">
            <strong>Trage fisierul aici</strong><br>
            <span class="text-secondary small">sau click pentru a alege</span><br>
            <small id="nameShopInventory" class="text-info"></small>
          </div>
        </div>
      </div>
    </div>

    <div class="mb-3">
      <button id="btnRunShop" class="btn btn-primary" disabled>Genereaza CSV pentru Shopify</button>
    </div>

    <div id="statusShop" class="status mb-2"></div>

    <div id="resultShop" hidden>
      <div id="summaryShop" class="d-flex flex-wrap gap-2 mb-3"></div>
      <div class="mb-3">
        <button id="btnDownloadShop" class="btn btn-success">⬇ Descarca .csv pentru Shopify</button>
      </div>
      <div id="issuesShop"></div>
    </div>
  </div>
</div>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='js/stocuri-shopify.js') }}"></script>
{% endblock %}
```

- [ ] **Commit**
```
git add app/templates/stocuri/shopify.html
git commit -m "feat: add API mode tab to Shopify page (keeps CSV tab)"
```

---

## Task 7 — Update JavaScript

**Files:**
- Modify: `app/static/js/stocuri-shopify.js`

Replace the entire file. `inventory_item_id` is a string (Shopify GID) throughout — used as the row key in `_selectedIds` Set and passed back in the sync payload. No other functional differences from the REST plan.

- [ ] **Replace the full file**

```javascript
// ───────────── Shared utilities ─────────────
function setupDropzone(zoneId, inputId, nameId, onChange) {
  const zone  = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const name  = document.getElementById(nameId);
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("dragover"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragover"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault(); zone.classList.remove("dragover");
    if (e.dataTransfer.files.length) handle(e.dataTransfer.files[0]);
  });
  input.addEventListener("change", (e) => { if (e.target.files.length) handle(e.target.files[0]); });
  function handle(f) {
    name.textContent = `Selectat: ${f.name}`;
    zone.classList.add("has-file");
    onChange(f);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

function issueBlock(kind, title, items) {
  const list = items.slice(0, 200).map((x) => `<li>${escapeHtml(String(x))}</li>`).join("");
  const more = items.length > 200 ? `<div class="text-secondary mt-1">… si inca ${items.length - 200}</div>` : "";
  return `<div class="issue-block mb-2">
    <div class="issue-head ${kind} d-flex justify-content-between align-items-center p-2 rounded" style="cursor:pointer;">
      <span>${escapeHtml(title)}</span><span class="badge bg-secondary">${items.length}</span>
    </div>
    <div class="issue-body p-2" hidden><ul class="mb-0">${list}</ul>${more}</div>
  </div>`;
}

function triggerDownload(b64, filename, mime) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const blob  = new Blob([bytes], { type: mime || "text/csv" });
  const url   = URL.createObjectURL(blob);
  const a     = document.createElement("a");
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 300);
}

// ───────────── Tab switcher ─────────────
document.querySelectorAll("#shopTabs .nav-link").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#shopTabs .nav-link").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.getElementById("tabApi").hidden = tab !== "api";
    document.getElementById("tabCsv").hidden = tab !== "csv";
  });
});

// ───────────── API mode — connection indicator ─────────────
const SHOP_CONN_INTERVAL_MS = 3 * 60 * 1000;
const shopConnDot = document.getElementById("shopConnDot");
let _shopConnTimer = null;

function shopConnStart() {
  shopConnStop();
  shopConnCheck();
  _shopConnTimer = setInterval(shopConnCheck, SHOP_CONN_INTERVAL_MS);
  document.addEventListener("visibilitychange", _shopVisChange);
}
function shopConnStop() {
  clearInterval(_shopConnTimer); _shopConnTimer = null;
  document.removeEventListener("visibilitychange", _shopVisChange);
}
function _shopVisChange() {
  if (document.hidden) { clearInterval(_shopConnTimer); _shopConnTimer = null; }
  else { shopConnCheck(); _shopConnTimer = setInterval(shopConnCheck, SHOP_CONN_INTERVAL_MS); }
}
async function shopConnCheck() {
  _setShopDot("loading", "Verific conexiunea Shopify...");
  try {
    const resp = await fetch("/api/stocuri/shopify/connection-test");
    const data = await resp.json();
    if (data.ok) _setShopDot("ok", `Conectat: ${data.shop_name || data.shop_domain}`);
    else          _setShopDot("error", data.error || "Conexiune esuata");
  } catch (e) {
    _setShopDot("error", "Eroare retea: " + e.message);
  }
}
function _setShopDot(state, title) {
  shopConnDot.className = "conn-dot conn-dot--" + state;
  shopConnDot.title = title;
}
shopConnStart();

// ───────────── API mode — state ─────────────
let shopApiReportFile = null;

const btnShopApiPreview     = document.getElementById("btnShopApiPreview");
const btnShopApiSync        = document.getElementById("btnShopApiSync");
const shopApiStatusEl       = document.getElementById("shopApiStatus");
const shopApiPreviewSection = document.getElementById("shopApiPreviewSection");
const shopApiSummaryEl      = document.getElementById("shopApiSummary");
const shopApiTableBody      = document.getElementById("shopApiTableBody");
const shopApiIssuesEl       = document.getElementById("shopApiIssues");
const shopApiSyncResults    = document.getElementById("shopApiSyncResults");
const shopApiSyncSummaryEl  = document.getElementById("shopApiSyncSummary");
const shopApiSyncErrorsEl   = document.getElementById("shopApiSyncErrors");
const shopApiSelectAll      = document.getElementById("shopApiSelectAll");
const shopApiToolbarEl      = document.getElementById("shopApiToolbar");
const shopApiFilterEl       = document.getElementById("shopApiFilter");
const shopApiPaginationInfo = document.getElementById("shopApiPaginationInfo");
const shopApiPrevPageBtn    = document.getElementById("shopApiPrevPage");
const shopApiNextPageBtn    = document.getElementById("shopApiNextPage");

// ───────────── PaginationController ─────────────
class PaginationController {
  constructor({ pageSize, tableBody, infoEl, prevEl, nextEl }) {
    this._all = []; this._filtered = []; this._selectedIds = new Set();
    this._page = 0; this._pageSize = pageSize;
    this._tableBody = tableBody; this._infoEl = infoEl;
    this._prevEl = prevEl; this._nextEl = nextEl;
    this._sortKey = null; this._sortDir = "asc";
    prevEl.addEventListener("click", () => this._goTo(this._page - 1));
    nextEl.addEventListener("click", () => this._goTo(this._page + 1));
    tableBody.addEventListener("change", (e) => {
      const cb = e.target.closest(".shop-row-check");
      if (!cb) return;
      const id = cb.dataset.iid;
      if (cb.checked) this._selectedIds.add(id); else this._selectedIds.delete(id);
    });
  }
  setRows(rows) {
    this._all = rows; this._filtered = [...rows];
    this._selectedIds = new Set(
      rows.filter((r) => r.status === "updated" || r.status === "zeroed_threshold")
          .map((r) => r.inventory_item_id)
    );
    this._applySort(); this._goTo(0);
  }
  setFilter(status) {
    this._filtered = status ? this._all.filter((r) => r.status === status) : [...this._all];
    this._applySort(); this._goTo(0);
  }
  setSort(key) {
    if (this._sortKey === key) this._sortDir = this._sortDir === "asc" ? "desc" : "asc";
    else { this._sortKey = key; this._sortDir = "asc"; }
    this._applySort(); this._goTo(0);
  }
  getSortState() { return { key: this._sortKey, dir: this._sortDir }; }
  _applySort() {
    if (!this._sortKey) return;
    const key = this._sortKey; const dir = this._sortDir === "asc" ? 1 : -1;
    this._filtered = [...this._filtered].sort((a, b) => {
      let av = a[key], bv = b[key];
      if (av == null) return 1; if (bv == null) return -1;
      if (typeof av === "string") return av.localeCompare(bv, "ro") * dir;
      return (av - bv) * dir;
    });
  }
  selectAll(checked) {
    this._filtered.forEach((r) => {
      const canUpdate = r.status === "updated" || r.status === "zeroed_threshold";
      if (!canUpdate) return;
      if (checked) this._selectedIds.add(r.inventory_item_id);
      else         this._selectedIds.delete(r.inventory_item_id);
    });
    this._renderPage();
  }
  getSelectedRows() {
    return this._all.filter((r) => this._selectedIds.has(r.inventory_item_id));
  }
  _goTo(page) {
    const total = this._filtered.length;
    const maxPage = Math.max(0, Math.ceil(total / this._pageSize) - 1);
    this._page = Math.max(0, Math.min(page, maxPage));
    this._renderPage();
  }
  _renderPage() {
    const total = this._filtered.length;
    const start = this._page * this._pageSize;
    const end = start + this._pageSize;
    this._tableBody.innerHTML = this._filtered.slice(start, end)
      .map((r) => renderShopApiRow(r, this._selectedIds)).join("");
    this._infoEl.textContent = total === 0
      ? "0 variante"
      : `Afisezi ${start + 1}–${Math.min(end, total)} din ${total} variante`;
    this._prevEl.disabled = this._page === 0;
    this._nextEl.disabled = end >= total;
  }
}

const SHOP_STATUS_LABEL = {
  updated:          '<span class="badge bg-success">Actualizat</span>',
  zeroed_threshold: '<span class="badge bg-warning text-dark">Zerificate (stoc mic)</span>',
  unchanged:        '<span class="badge bg-secondary">Nemodificat</span>',
  no_sku:           '<span class="badge bg-secondary">Fara SKU</span>',
  no_report:        '<span class="badge bg-secondary">–</span>',
};

function renderShopApiRow(r, selectedIds) {
  const canUpdate = r.status === "updated" || r.status === "zeroed_threshold";
  const isChecked = selectedIds && selectedIds.has(r.inventory_item_id);
  const newStockCell = r.new_stock !== null && r.new_stock !== undefined
    ? r.new_stock : '<span class="text-secondary">–</span>';
  return `<tr class="emag-row emag-row--${r.status}">
    <td><input type="checkbox" class="shop-row-check"
         data-iid="${escapeHtml(r.inventory_item_id)}"
         ${canUpdate ? (isChecked ? "checked" : "") : "disabled"} /></td>
    <td class="emag-name">${escapeHtml(r.name)}</td>
    <td><code>${escapeHtml(r.sku || "—")}</code></td>
    <td style="text-align:right;">${r.old_stock}</td>
    <td style="text-align:right;">${newStockCell}</td>
    <td>${SHOP_STATUS_LABEL[r.status] || escapeHtml(r.status)}</td>
  </tr>`;
}

const shopApiPagination = new PaginationController({
  pageSize: 50, tableBody: shopApiTableBody,
  infoEl: shopApiPaginationInfo, prevEl: shopApiPrevPageBtn, nextEl: shopApiNextPageBtn,
});

shopApiFilterEl.addEventListener("change", () => shopApiPagination.setFilter(shopApiFilterEl.value));
shopApiSelectAll.addEventListener("change", () => shopApiPagination.selectAll(shopApiSelectAll.checked));

document.querySelectorAll("#shopApiTable thead th[data-sort]").forEach((th) => {
  th.addEventListener("click", () => {
    shopApiPagination.setSort(th.dataset.sort);
    updateShopApiSortHeaders();
  });
});

function updateShopApiSortHeaders() {
  const { key, dir } = shopApiPagination.getSortState();
  document.querySelectorAll("#shopApiTable thead th[data-sort]").forEach((th) => {
    th.classList.toggle("sort-asc",  th.dataset.sort === key && dir === "asc");
    th.classList.toggle("sort-desc", th.dataset.sort === key && dir === "desc");
  });
}

setupDropzone("dzShopApiReport", "fileShopApiReport", "nameShopApiReport", (f) => {
  shopApiReportFile = f;
  runShopApiPreview();
});

btnShopApiPreview.addEventListener("click", runShopApiPreview);
btnShopApiSync.addEventListener("click", runShopApiSync);

async function runShopApiPreview() {
  setShopApiStatus("", "");
  btnShopApiPreview.disabled  = true;
  btnShopApiPreview.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se incarca...';
  shopApiPreviewSection.hidden = true;
  shopApiSyncResults.hidden    = true;

  const fd = new FormData();
  if (shopApiReportFile) fd.append("raport", shopApiReportFile);

  try {
    const resp = await fetch("/api/stocuri/shopify/preview", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) { setShopApiStatus(data.error || "Eroare necunoscuta", "error"); return; }
    renderShopApiPreview(data);
    const msg = data.has_report
      ? `Gata. ${data.summary.to_update} variante vor fi actualizate.`
      : `Gata. ${data.summary.total_shopify_variants} variante preluate din Shopify.`;
    setShopApiStatus(msg, "success");
  } catch (e) {
    setShopApiStatus("Eroare retea: " + e.message, "error");
  } finally {
    btnShopApiPreview.disabled   = false;
    btnShopApiPreview.textContent = "Incarca stoc Shopify";
  }
}

function renderShopApiPreview(data) {
  const s = data.summary;
  if (data.has_report) {
    shopApiSummaryEl.className = "d-flex flex-wrap gap-2 mb-3";
    shopApiSummaryEl.innerHTML = `
      <div class="stat"><div class="label">Total variante Shopify</div><div class="value">${s.total_shopify_variants}</div></div>
      <div class="stat success"><div class="label">De actualizat (stoc real)</div><div class="value">${s.updated_with_stock}</div></div>
      <div class="stat warning"><div class="label">Zerificate (stoc &le; ${s.safety_threshold})</div><div class="value">${s.zeroed_threshold}</div></div>
      <div class="stat muted"><div class="label">Nemodificate</div><div class="value">${s.unchanged}</div></div>
      <div class="stat muted"><div class="label">Fara SKU pe Shopify</div><div class="value">${s.no_sku}</div></div>
      <div class="stat muted"><div class="label">SKU-uri negasite pe Shopify</div><div class="value">${s.not_in_shopify}</div></div>`;
  } else {
    shopApiSummaryEl.className = "emag-summary-inline mb-2";
    shopApiSummaryEl.innerHTML = `${s.total_shopify_variants} variante preluate din Shopify`
      + (s.no_sku > 0 ? ` &middot; <span class="emag-summary-warn">${s.no_sku} fara SKU</span>` : "");
  }

  btnShopApiSync.disabled = !data.has_report;
  shopApiToolbarEl.hidden = !data.has_report;
  if (!data.has_report) shopApiFilterEl.value = "";
  shopApiPagination.setRows(data.rows);
  updateShopApiSortHeaders();

  const blocks = [];
  if (data.has_report) {
    if (data.warnings && data.warnings.length)
      blocks.push(issueBlock("warning", "Avertismente parsare raport", data.warnings));
    if (data.skus_not_in_shopify && data.skus_not_in_shopify.length)
      blocks.push(issueBlock("warning", "SKU-uri din raport negasite pe Shopify",
        data.skus_not_in_shopify.map((r) => `SKU ${r.sku} — qty ${r.qty}`)));
  }
  shopApiIssuesEl.innerHTML = blocks.join("");
  shopApiIssuesEl.querySelectorAll(".issue-head").forEach((h) => {
    h.addEventListener("click", () => { h.nextElementSibling.hidden = !h.nextElementSibling.hidden; });
  });
  shopApiPreviewSection.hidden = false;
}

async function runShopApiSync() {
  const selectedRows = shopApiPagination.getSelectedRows();
  if (!selectedRows.length) {
    setShopApiStatus("Nicio linie selectata pentru sincronizare.", "error"); return;
  }
  const changed = selectedRows.filter(
    (r) => r.new_stock !== null && r.new_stock !== undefined && r.new_stock !== r.old_stock
  );
  if (!changed.length) {
    setShopApiStatus("Niciun stoc modificat fata de Shopify. Nimic de sincronizat.", "warning"); return;
  }
  const skipped = selectedRows.length - changed.length;
  const rows_to_update = changed.map((r) => ({
    inventory_item_id: r.inventory_item_id,
    sku:               r.sku || "",
    name:              r.name,
    new_stock:         r.new_stock,
  }));

  setShopApiStatus("", "");
  btnShopApiSync.disabled  = true;
  btnShopApiSync.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Se trimit...';

  try {
    const resp = await fetch("/api/stocuri/shopify/sync", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rows_to_update }),
    });
    const data = await resp.json();
    if (!resp.ok) { setShopApiStatus(data.error || "Eroare necunoscuta", "error"); return; }
    renderShopApiSyncResults(data);
    const skipNote = skipped > 0 ? ` (${skipped} nemodificate, sarite)` : "";
    setShopApiStatus(
      `Sincronizare finalizata: ${data.success_count} succes, ${data.error_count} erori${skipNote}.`,
      data.error_count ? "warning" : "success"
    );
  } catch (e) {
    setShopApiStatus("Eroare retea: " + e.message, "error");
  } finally {
    btnShopApiSync.disabled   = false;
    btnShopApiSync.textContent = "Sincronizeaza pe Shopify";
  }
}

function renderShopApiSyncResults(data) {
  const errors = data.results.filter((r) => !r.ok);
  shopApiSyncSummaryEl.innerHTML = `
    <div class="stat success"><div class="label">Actualizate cu succes</div><div class="value">${data.success_count}</div></div>
    <div class="stat ${data.error_count ? "warning" : "muted"}"><div class="label">Erori</div><div class="value">${data.error_count}</div></div>`;
  shopApiSyncErrorsEl.innerHTML = errors.length
    ? issueBlock("warning", "Variante care nu au putut fi actualizate",
        errors.map((r) => `${r.name} (SKU ${r.sku || "—"}): ${r.error}`))
    : "";
  if (errors.length) {
    shopApiSyncErrorsEl.querySelectorAll(".issue-head").forEach((h) => {
      h.addEventListener("click", () => { h.nextElementSibling.hidden = !h.nextElementSibling.hidden; });
    });
  }
  shopApiSyncResults.hidden = false;
}

function setShopApiStatus(msg, kind) {
  if (kind === "busy") {
    shopApiStatusEl.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${escapeHtml(msg)}`;
  } else {
    shopApiStatusEl.textContent = msg;
  }
  shopApiStatusEl.className = "status" + (kind ? " " + kind : "");
}

// ───────────── CSV mode (unchanged) ─────────────
let shopReportFile    = null;
let shopInventoryFile = null;
let shopLastResult    = null;

const btnRunShop      = document.getElementById("btnRunShop");
const btnDownloadShop = document.getElementById("btnDownloadShop");
const statusShopEl    = document.getElementById("statusShop");
const resultShopEl    = document.getElementById("resultShop");
const summaryShopEl   = document.getElementById("summaryShop");
const issuesShopEl    = document.getElementById("issuesShop");

setupDropzone("dzShopReport", "fileShopReport", "nameShopReport", (f) => {
  shopReportFile = f;
  btnRunShop.disabled = !(shopReportFile && shopInventoryFile);
});
setupDropzone("dzShopInventory", "fileShopInventory", "nameShopInventory", (f) => {
  shopInventoryFile = f;
  btnRunShop.disabled = !(shopReportFile && shopInventoryFile);
});

btnRunShop.addEventListener("click", runShop);
btnDownloadShop.addEventListener("click", () => {
  if (shopLastResult) triggerDownload(shopLastResult.file_b64, shopLastResult.filename, "text/csv");
});

async function runShop() {
  setStatusShop("Procesez fisierele...", "busy");
  btnRunShop.disabled  = true;
  btnRunShop.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Procesez...';
  resultShopEl.hidden  = true;

  const fd = new FormData();
  fd.append("raport", shopReportFile);
  fd.append("inventory", shopInventoryFile);

  try {
    const resp = await fetch("/api/stocuri/shopify/run", { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok) { setStatusShop(data.error || "Eroare necunoscuta", "error"); return; }
    shopLastResult = data;
    renderShopResult(data);
    setStatusShop("Gata. Verifica sumarul si descarca CSV-ul.", "success");
  } catch (e) {
    setStatusShop("Eroare retea: " + e.message, "error");
  } finally {
    btnRunShop.disabled   = !(shopReportFile && shopInventoryFile);
    btnRunShop.textContent = "Genereaza CSV pentru Shopify";
  }
}

function setStatusShop(msg, kind) {
  if (kind === "busy") {
    statusShopEl.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${escapeHtml(msg)}`;
  } else {
    statusShopEl.textContent = msg;
  }
  statusShopEl.className = "status" + (kind ? " " + kind : "");
}

function renderShopResult(data) {
  resultShopEl.hidden = false;
  const s = data.summary;
  summaryShopEl.innerHTML = `
    <div class="stat"><div class="label">Randuri raport</div><div class="value">${s.report_total_rows}</div></div>
    <div class="stat"><div class="label">SKU-uri cu codmare</div><div class="value">${s.report_skus_with_codmare}</div></div>
    <div class="stat success"><div class="label">Active pe Shopify</div><div class="value">${s.shopify_active}</div></div>
    <div class="stat warning"><div class="label">Zerificate: stoc &le; ${s.safety_threshold}</div><div class="value">${s.shopify_zero_low_stock}</div></div>
    <div class="stat warning"><div class="label">Zerificate: nu sunt in raport</div><div class="value">${s.shopify_zero_not_in_report}</div></div>
    <div class="stat muted"><div class="label">Codmare negasit pe Shopify</div><div class="value">${s.codmare_not_in_shopify}</div></div>
    <div class="stat muted"><div class="label">Randuri alte locatii (neatinse)</div><div class="value">${s.shopify_rows_other_location}</div></div>`;
  const blocks = [];
  if (data.warnings && data.warnings.length)
    blocks.push(issueBlock("warning", "Avertismente parsare", data.warnings));
  if (data.codmare_below_threshold && data.codmare_below_threshold.length)
    blocks.push(issueBlock("warning", `Produse cu stoc mic (≤ ${s.safety_threshold}) — trimise ca 0 pe Shopify`,
      data.codmare_below_threshold.map((r) => `codmare ${r.codmare} — stoc real ${r.qty_real}`)));
  if (data.codmare_not_in_shopify && data.codmare_not_in_shopify.length)
    blocks.push(issueBlock("warning", "Codmare din raport care NU exista pe Shopify", data.codmare_not_in_shopify));
  if (data.skus_no_codmare && data.skus_no_codmare.length)
    blocks.push(issueBlock("warning", "SKU-uri fara codmare (sarite)",
      data.skus_no_codmare.map((r) => `SKU ${r.sku} — qty ${r.qty}`)));
  issuesShopEl.innerHTML = blocks.join("");
  issuesShopEl.querySelectorAll(".issue-head").forEach((h) => {
    h.addEventListener("click", () => { h.nextElementSibling.hidden = !h.nextElementSibling.hidden; });
  });
}
```

- [ ] **Commit**
```
git add app/static/js/stocuri-shopify.js
git commit -m "feat: add GraphQL API mode to Shopify JS (connection dot, preview table, sync)"
```

---

## Self-Review

**Spec coverage:**
- ✅ GraphQL API throughout — `gql[httpx]`, `HTTPXAsyncTransport`
- ✅ `gql[httpx]` added to `requirements.txt`
- ✅ Bulk inventory via `inventorySetQuantities` (100 items/call, not 1/call)
- ✅ IDs are Shopify GIDs (strings) consistently in Python and JS
- ✅ Location GID constructed from numeric `.env` value — user stores only the number
- ✅ Connection test returns locations with both numeric `id` (for `.env`) and full `gid`
- ✅ `location(id: $locationId)` null-check — raises clear error if location ID is wrong
- ✅ Cursor-based pagination for variants and inventory levels
- ✅ `displayName` used for variant name (returns "Product / Variant" automatically)
- ✅ `_norm` applied symmetrically to Shopify SKU and report codmare
- ✅ Only changed stocks sent to sync (client-side filter)
- ✅ Request logger saves to `logs/shopify_req.json`, max 20 entries
- ✅ CSV mode completely preserved

**Placeholder scan:** No TBDs, TODOs, or incomplete steps found.

**Type consistency:**
- `inventory_item_id`: `str` (GID) in `PreviewRow`, orchestrator, JS `_selectedIds` Set, sync payload — consistent throughout
- `_selectedIds.has(r.inventory_item_id)` uses the raw GID string as key — no `String()` conversion needed since it's already a string
- `bulk_set_inventory` receives `inventory_item_id` as string and passes it directly to `inventoryItemId` in the mutation — correct
