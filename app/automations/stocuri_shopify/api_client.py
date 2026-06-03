"""Shopify GraphQL Admin API client — OAuth 2.0 client credentials, token auto-refresh."""

import asyncio
import logging
import time

import httpx

from config import settings
from . import request_logger

log = logging.getLogger(__name__)

BATCH_SIZE = 50
_TOKEN_REFRESH_MARGIN = 300  # refresh 5 min before expiry


def _to_location_gid(raw: str) -> str:
    raw = raw.strip()
    return raw if raw.startswith("gid://") else f"gid://shopify/Location/{raw}"


class _TokenCache:
    def __init__(self):
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self, shop: str, client_id: str, client_secret: str) -> str:
        async with self._lock:
            if self._token and time.time() < self._expires_at - _TOKEN_REFRESH_MARGIN:
                return self._token
            url = f"https://{shop}/admin/oauth/access_token"
            log_payload = {"client_id": client_id, "client_secret": "***", "grant_type": "client_credentials"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                with request_logger.capture(url=url, payload=log_payload) as ctx:
                    resp = await client.post(url, json={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"})
                    ctx.status_code = resp.status_code
                    ctx.response_text = resp.text
                    resp.raise_for_status()
                    data = resp.json()
            token = data.get("access_token")
            if not token:
                raise RuntimeError(f"Shopify token response missing access_token: {data}")
            self._token = token
            self._expires_at = time.time() + data.get("expires_in", 86400)
            log.info("Shopify token refreshed, expires in %ds", data.get("expires_in", 86400))
            return self._token


_cache = _TokenCache()

_Q_LOCATIONS = "query { locations(first: 20) { nodes { id name } } }"

_Q_INVENTORY = """
query GetInventory($locationId: ID!, $cursor: String) {
  location(id: $locationId) {
    inventoryLevels(first: 50, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes {
        item {
          id
          sku
          variant { displayName product { title } }
        }
        quantities(names: ["on_hand"]) { name quantity }
      }
    }
  }
}
"""

_M_SET_ON_HAND = """
mutation SetOnHand($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) {
    inventoryAdjustmentGroup { id }
    userErrors { field message code }
  }
}
"""


class ShopifyClient:
    def __init__(self):
        self._shop = settings.shopify_shop_domain.strip()
        self._client_id = settings.shopify_client_id.strip()
        self._client_secret = settings.shopify_client_secret.strip()
        ver = settings.shopify_api_version or "2025-04"
        self._gql_url = f"https://{self._shop}/admin/api/{ver}/graphql.json"
        self._location_gid = _to_location_gid(settings.shopify_location_id) if settings.shopify_location_id else None

    def _check(self):
        if not self._shop or not self._client_id or not self._client_secret:
            raise RuntimeError("Shopify not configured. Set SHOPIFY_SHOP_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET in .env")

    async def _graphql(self, query: str, variables: dict | None = None) -> dict:
        token = await _cache.get(self._shop, self._client_id, self._client_secret)
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        async with httpx.AsyncClient(timeout=30.0) as client:
            with request_logger.capture(url=self._gql_url, payload=payload) as ctx:
                resp = await client.post(
                    self._gql_url, json=payload,
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                )
                ctx.status_code = resp.status_code
                ctx.response_text = resp.text
                resp.raise_for_status()
                return resp.json()

    async def test_connection(self) -> list[dict]:
        self._check()
        data = await self._graphql(_Q_LOCATIONS)
        locations = data["data"]["locations"]["nodes"]
        if not locations:
            raise RuntimeError("Connected but no locations returned.")
        return locations

    async def fetch_all_inventory(self) -> list[dict]:
        self._check()
        if not self._location_gid:
            raise RuntimeError("SHOPIFY_LOCATION_ID not set. Run connection-test to see available locations.")

        items: list[dict] = []
        cursor = None
        while True:
            data = await self._graphql(_Q_INVENTORY, {"locationId": self._location_gid, "cursor": cursor})
            loc = (data.get("data") or {}).get("location")
            if not loc:
                raise RuntimeError(f"Shopify GraphQL error: {data.get('errors') or data}")

            for node in loc["inventoryLevels"]["nodes"]:
                inv = node["item"]
                variant = inv.get("variant") or {}
                product_title = (variant.get("product") or {}).get("title", "")
                display = variant.get("displayName", "")
                name = f"{product_title} — {display}".strip(" —")
                on_hand = next((q["quantity"] for q in (node.get("quantities") or []) if q["name"] == "on_hand"), 0)
                items.append({
                    "inventory_item_id": inv["id"],
                    "sku": (inv.get("sku") or "").strip(),
                    "name": name,
                    "on_hand": on_hand,
                })

            page = loc["inventoryLevels"]["pageInfo"]
            if not page["hasNextPage"]:
                break
            cursor = page["endCursor"]

        return items

    async def set_on_hand_quantities(self, updates: list[dict]) -> list[dict]:
        self._check()
        if not self._location_gid:
            raise RuntimeError("SHOPIFY_LOCATION_ID not set.")

        results: list[dict] = []
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i: i + BATCH_SIZE]
            variables = {
                "input": {
                    "name": "on_hand",
                    "reason": "correction",
                    "referenceDocumentUri": "torb://stoc-sync",
                    "ignoreCompareQuantity": True,
                    "quantities": [
                        {
                            "inventoryItemId": u["inventory_item_id"],
                            "locationId": self._location_gid,
                            "quantity": u["new_stock"],
                        }
                        for u in batch
                    ],
                }
            }
            try:
                data = await self._graphql(_M_SET_ON_HAND, variables)
                gql_errors = data.get("errors")
                if gql_errors:
                    err = str(gql_errors)
                    for u in batch:
                        results.append({**u, "ok": False, "error": err})
                    continue
                user_errors = (data["data"]["inventorySetQuantities"].get("userErrors")) or []
                if user_errors:
                    err = "; ".join(f"{e['field']}: {e['message']}" for e in user_errors)
                    for u in batch:
                        results.append({**u, "ok": False, "error": err})
                else:
                    for u in batch:
                        results.append({**u, "ok": True, "error": None})
            except Exception as exc:
                for u in batch:
                    results.append({**u, "ok": False, "error": str(exc)})

        return results
