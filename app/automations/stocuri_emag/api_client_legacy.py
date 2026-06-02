import hashlib
import logging
import httpx

from config import settings

log = logging.getLogger(__name__)


class EmagClient:
    """Client pentru eMAG Marketplace API.

    Autentificare: Basic Auth cu parola hashed in MD5 (asa cere eMAG).
    Documentatie: https://marketplace.emag.ro/api-3/

    Flow pentru sincronizare stoc dupa EAN:
      1. fetch_all_offers() — citeste toate ofertele mele si le indexeaza dupa EAN
      2. update_stock(offer_id, warehouse_id, qty) — patch stocul pentru o oferta
    """

    def __init__(self):
        self.base_url = settings.emag_api_url.rstrip("/")
        self.username = settings.emag_username
        password_md5 = (
            hashlib.md5(settings.emag_password.encode("utf-8")).hexdigest()
            if settings.emag_password
            else ""
        )
        self._auth = (self.username, password_md5)
        self._timeout = httpx.Timeout(30.0, connect=10.0)

    def _check_configured(self):
        if not self.username or not settings.emag_password:
            raise RuntimeError(
                "eMAG API nu este configurat. Completeaza EMAG_USERNAME si EMAG_PASSWORD in .env"
            )

    async def fetch_all_offers(self) -> dict[str, dict]:
        """Returneaza dict {ean: offer} pentru toate ofertele active."""
        self._check_configured()
        offers_by_ean: dict[str, dict] = {}
        page = 1
        per_page = 100
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            while True:
                resp = await client.post(
                    f"{self.base_url}/product_offer/read",
                    json={"currentPage": page, "itemsPerPage": per_page},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("isError"):
                    raise RuntimeError(f"eMAG read error: {data.get('messages')}")
                results = data.get("results") or []
                if not results:
                    break
                for offer in results:
                    eans = offer.get("ean") or []
                    if isinstance(eans, str):
                        eans = [eans]
                    for ean in eans:
                        ean_clean = str(ean).strip()
                        if ean_clean:
                            offers_by_ean[ean_clean] = offer
                if len(results) < per_page:
                    break
                page += 1
        return offers_by_ean

    async def update_stock(self, offer_id: int, warehouse_id: int, qty: int) -> tuple[bool, str]:
        """Actualizeaza stocul unei oferte (endpoint lightweight, doar stoc, nu pret)."""
        self._check_configured()
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            resp = await client.patch(
                f"{self.base_url}/offer_stock/{offer_id}",
                json={"stock": [{"warehouse_id": warehouse_id, "value": qty}]},
            )
            try:
                data = resp.json()
            except Exception:
                return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
            if data.get("isError"):
                return False, str(data.get("messages") or data)
            return True, "OK"
