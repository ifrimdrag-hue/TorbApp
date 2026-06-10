import logging
import httpx

from config import settings
from . import request_logger

log = logging.getLogger(__name__)

BATCH_SIZE = 50  # eMAG bulk save limit per request


class EmagClient:
    """Client for the eMAG Marketplace API.

    Authentication: standard HTTP Basic Auth with plain-text password,
    as specified in the official API documentation v4.5.1.
    """

    def __init__(self):
        self.base_url = settings.emag_api_url.rstrip("/")
        self._auth = (settings.emag_username, settings.emag_password)
        self._timeout = httpx.Timeout(30.0, connect=10.0)

    def _check_configured(self):
        if not settings.emag_username or not settings.emag_password:
            raise RuntimeError(
                "eMAG API not configured. Set EMAG_USERNAME and EMAG_PASSWORD in .env"
            )

    async def test_connection(self) -> None:
        """Ping eMAG API using product_offer/count. Raises on any failure."""
        self._check_configured()
        url = f"{self.base_url}/product_offer/count"
        payload = {}
        timeout = httpx.Timeout(8.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, auth=self._auth) as client:
            with request_logger.capture(url=url, payload=payload) as ctx:
                resp = await client.post(url, json=payload)
                ctx.status_code = resp.status_code
                ctx.response_text = resp.text
                resp.raise_for_status()
                data = resp.json()
                if data.get("isError"):
                    raise RuntimeError(str(data.get("messages") or "API error"))

    async def fetch_all_offers_raw(self) -> list[dict]:
        """Fetch all seller offers as a raw list, paginated."""
        self._check_configured()
        all_offers: list[dict] = []
        page = 1
        per_page = 100
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            while True:
                url = f"{self.base_url}/product_offer/read"
                payload = {"currentPage": page, "itemsPerPage": per_page, "status": 1}
                with request_logger.capture(url=url, payload=payload) as ctx:
                    resp = await client.post(url, json=payload)
                    ctx.status_code = resp.status_code
                    ctx.response_text = resp.text
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("isError"):
                        raise RuntimeError(f"eMAG API error: {data.get('messages')}")
                results = data.get("results") or []
                all_offers.extend(results)
                if len(results) < per_page:
                    break
                page += 1
        return all_offers

    async def bulk_update_stock(self, updates: list[dict]) -> list[dict]:
        """Update stock for multiple offers using the light offer/save bulk API.

        Uses POST /offer/save with batches of up to 50 items to stay within
        eMAG rate limits (3 req/sec cumulative for non-order resources).

        Args:
            updates: list of {"id": offer_id, "stock": qty}

        Returns:
            list of {"id": offer_id, "ok": bool, "error": str | None}
        """
        self._check_configured()
        results: list[dict] = []

        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            for i in range(0, len(updates), BATCH_SIZE):
                batch = updates[i : i + BATCH_SIZE]
                url = f"{self.base_url}/offer/save"
                try:
                    with request_logger.capture(url=url, payload=batch) as ctx:
                        resp = await client.post(url, json=batch)
                        ctx.status_code = resp.status_code
                        ctx.response_text = resp.text
                        data = resp.json()

                    if data.get("isError"):
                        error_msg = str(data.get("messages") or "Unknown eMAG error")
                        for item in batch:
                            results.append({"id": item["id"], "ok": False, "error": error_msg})
                        continue

                    batch_results = data.get("results") or []
                    if isinstance(batch_results, list) and len(batch_results) == len(batch):
                        for item, result in zip(batch, batch_results):
                            ok = not result.get("isError", False)
                            error = str(result.get("messages") or "") if not ok else None
                            results.append({"id": item["id"], "ok": ok, "error": error})
                    else:
                        # Bulk accepted, no per-item errors returned
                        for item in batch:
                            results.append({"id": item["id"], "ok": True, "error": None})

                except Exception as e:
                    for item in batch:
                        results.append({"id": item["id"], "ok": False, "error": str(e)})

        return results
