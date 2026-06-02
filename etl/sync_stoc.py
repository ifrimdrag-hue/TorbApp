"""
Sincronizare stocuri: ERP (fișier .xls) → eMAG Marketplace + Shopify

Cum funcționează:
  1. Citește cel mai recent fișier stoc din docs_input/DD.MM.YYYY/stoc *.xls
  2. Agregă cantitățile pe EAN (codbare)
  3. Trimite update de stoc la eMAG prin Marketplace API v3
  4. Trimite update de stoc la Shopify prin Admin API

Configurare: copiază .env.example → .env și completează credențialele.

Rulare manuală:
    python sync_stoc.py

Opțiuni:
    python sync_stoc.py --only-emag      # doar eMAG
    python sync_stoc.py --only-shopify   # doar Shopify
    python sync_stoc.py --dry-run        # simulare fără modificări
    python sync_stoc.py <cale_fisier>    # fișier specific
"""

import sys
import os
import re
import json
import time
import logging
import argparse
from collections import defaultdict
from datetime import date, datetime

import requests
import xlrd
from dotenv import load_dotenv

# ── configurare ──────────────────────────────────────────────────────────────

load_dotenv()

DOCS_PATH = "docs_input"
LOG_PATH  = "logs/sync_stoc.log"

# eMAG Marketplace API v3
EMAG_BASE_URL = "https://marketplace.emag.ro/api-3"
EMAG_USERNAME = os.getenv("EMAG_USERNAME", "")
EMAG_API_KEY  = os.getenv("EMAG_API_KEY", "")

# Shopify Admin API
SHOPIFY_SHOP         = os.getenv("SHOPIFY_SHOP", "")          # ex: basilurtea.myshopify.com
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
SHOPIFY_LOCATION_ID  = os.getenv("SHOPIFY_LOCATION_ID", "")   # numeric ID
SHOPIFY_API_VERSION  = "2025-04"

# Pauza între apeluri API (secunde) — evită rate-limiting
EMAG_RATE_DELAY    = 0.3
SHOPIFY_RATE_DELAY = 0.5

# ── logging ───────────────────────────────────────────────────────────────────

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── citire fișier stoc ────────────────────────────────────────────────────────

def find_latest_stoc_file() -> tuple[date, str] | None:
    date_pattern = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
    candidates = []
    for entry in os.listdir(DOCS_PATH):
        if date_pattern.match(entry):
            folder = os.path.join(DOCS_PATH, entry)
            if os.path.isdir(folder):
                for f in os.listdir(folder):
                    if f.lower().startswith("stoc") and f.lower().endswith((".xls", ".xlsx")):
                        day, month, year = entry.split(".")
                        folder_date = date(int(year), int(month), int(day))
                        candidates.append((folder_date, os.path.join(folder, f)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0]


def read_stock_by_ean(filepath: str) -> dict[str, int]:
    """
    Citește fișierul stoc și returnează {ean: cantitate_totala}.
    Agregă toate loturile (mai multe rânduri cu același EAN).
    """
    log.info(f"Citesc fișier stoc: {filepath}")
    try:
        book = xlrd.open_workbook(filepath)
    except Exception as e:
        log.error(f"Nu pot deschide fișierul stoc: {e}")
        return {}

    ws = book.sheet_by_index(0)
    if ws.nrows < 2:
        log.warning("Fișier stoc gol.")
        return {}

    header = [str(ws.cell_value(0, c)).strip().lower() for c in range(ws.ncols)]
    try:
        idx_codbare = header.index("codbare")
        idx_cantit  = header.index("cantit")
    except ValueError:
        log.error(f"Coloane lipsă în fișierul stoc. Header găsit: {header}")
        return {}

    stocks: dict[str, float] = defaultdict(float)
    for row_idx in range(1, ws.nrows):
        ean = str(ws.cell_value(row_idx, idx_codbare)).strip()
        # Ignoră rânduri fără EAN sau EAN tip "0"
        if not ean or ean in ("0", "0.0", ""):
            continue
        # Normalizează EAN: elimină ".0" dacă xlrd a citit ca float
        if ean.endswith(".0"):
            ean = ean[:-2]
        try:
            qty = float(ws.cell_value(row_idx, idx_cantit) or 0)
        except (ValueError, TypeError):
            qty = 0.0
        stocks[ean] += qty

    result = {ean: max(0, int(round(qty))) for ean, qty in stocks.items()}
    log.info(f"  → {len(result)} EAN-uri unice, total unități: {sum(result.values()):,}")
    return result

# ── eMAG Marketplace API ──────────────────────────────────────────────────────

def emag_request(method: str, endpoint: str, payload=None, dry_run=False) -> dict | None:
    url  = f"{EMAG_BASE_URL}/{endpoint}"
    auth = (EMAG_USERNAME, EMAG_API_KEY)
    headers = {"Content-Type": "application/json"}
    try:
        if method == "GET" or payload is None:
            resp = requests.get(url, auth=auth, headers=headers, timeout=30)
        else:
            if dry_run and method == "POST" and "save" in endpoint:
                log.debug(f"  [DRY-RUN] POST {endpoint}: {json.dumps(payload)[:200]}")
                return {"isError": 0, "messages": [], "results": []}
            resp = requests.post(url, auth=auth, headers=headers,
                                 json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log.error(f"  eMAG request eșuat ({endpoint}): {e}")
        return None


def emag_get_all_offers() -> list[dict]:
    """Returnează toate ofertele active din contul eMAG (paginat)."""
    log.info("eMAG: citesc ofertele active...")
    offers = []
    page = 1
    per_page = 100
    while True:
        data = emag_request("POST", "offer/read", {
            "currentPage":   page,
            "itemsPerPage":  per_page,
        })
        if not data or data.get("isError"):
            log.error(f"  eMAG: eroare la citirea ofertelor (pagina {page}): {data}")
            break
        batch = data.get("results", [])
        if not batch:
            break
        offers.extend(batch)
        log.info(f"  Pagina {page}: {len(batch)} oferte (total până acum: {len(offers)})")
        if len(batch) < per_page:
            break
        page += 1
        time.sleep(EMAG_RATE_DELAY)

    log.info(f"  → Total oferte eMAG: {len(offers)}")
    return offers


def emag_sync_stock(stock_by_ean: dict[str, int], dry_run=False) -> dict:
    """Actualizează stocul pe eMAG pentru toate ofertele cu EAN din fișierul de stoc."""
    if not EMAG_USERNAME or not EMAG_API_KEY:
        log.warning("eMAG: credențiale lipsă (EMAG_USERNAME / EMAG_API_KEY). Sar peste.")
        return {"skipped": True}

    offers = emag_get_all_offers()
    if not offers:
        log.warning("eMAG: nicio ofertă găsită.")
        return {"updated": 0, "not_found": 0}

    # Construiesc mapare EAN → offer_id
    # eMAG stochează EAN în câmpul "part_number_key" sau "ean"
    ean_to_offer: dict[str, dict] = {}
    for offer in offers:
        # Câmpul principal de identificare după EAN
        pnk = str(offer.get("part_number_key", "") or "").strip()
        ean = str(offer.get("ean", "") or "").strip()
        key = pnk if pnk else ean
        if key and key != "0":
            ean_to_offer[key] = offer

    updated = 0
    not_found = 0
    errors = 0

    # Batch: eMAG acceptă mai multe oferte per apel (max recomandat: 100)
    batch_size = 50
    to_update = []
    for ean, qty in stock_by_ean.items():
        offer = ean_to_offer.get(ean)
        if offer is None:
            not_found += 1
            log.debug(f"  eMAG: EAN {ean} nu există în oferte — ignorat")
            continue
        to_update.append({
            "id":    offer["id"],
            "stock": qty,
        })

    log.info(f"eMAG: {len(to_update)} oferte de actualizat, {not_found} EAN-uri negăsite")

    for i in range(0, len(to_update), batch_size):
        batch = to_update[i:i + batch_size]
        result = emag_request("POST", "offer/save", batch, dry_run=dry_run)
        if result and not result.get("isError"):
            updated += len(batch)
            log.info(f"  Batch {i//batch_size + 1}: {len(batch)} oferte actualizate OK")
        else:
            errors += len(batch)
            log.error(f"  Batch {i//batch_size + 1}: eroare → {result}")
        time.sleep(EMAG_RATE_DELAY)

    log.info(f"eMAG: actualizat={updated}, negăsite={not_found}, erori={errors}")
    return {"updated": updated, "not_found": not_found, "errors": errors}

# ── Shopify Admin API ──────────────────────────────────────────────────────────

def shopify_headers() -> dict:
    return {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }


def shopify_get(endpoint: str, params: dict = None) -> dict | None:
    url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/{endpoint}"
    try:
        resp = requests.get(url, headers=shopify_headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log.error(f"  Shopify GET {endpoint}: {e}")
        return None


def shopify_post(endpoint: str, payload: dict, dry_run=False) -> dict | None:
    if dry_run:
        log.debug(f"  [DRY-RUN] Shopify POST {endpoint}: {json.dumps(payload)[:200]}")
        return {"inventory_level": {}}
    url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/{endpoint}"
    try:
        resp = requests.post(url, headers=shopify_headers(), json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        log.error(f"  Shopify POST {endpoint}: {e}")
        return None


def shopify_get_barcode_map() -> dict[str, int]:
    """
    Returnează {barcode: inventory_item_id} pentru toate variantele din magazin.
    Paginare prin link header (cursor-based).
    """
    log.info("Shopify: citesc produsele și variantele...")
    barcode_to_inv_item: dict[str, int] = {}
    params = {"limit": 250, "fields": "id,title,variants"}
    url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/products.json"

    while url:
        try:
            resp = requests.get(url, headers=shopify_headers(), params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            log.error(f"  Shopify: eroare la citirea produselor: {e}")
            break

        for product in data.get("products", []):
            for variant in product.get("variants", []):
                barcode = str(variant.get("barcode") or "").strip()
                if barcode and barcode != "0":
                    barcode_to_inv_item[barcode] = variant["inventory_item_id"]

        # Shopify paginare prin Link header
        link_header = resp.headers.get("Link", "")
        next_url = None
        for part in link_header.split(","):
            part = part.strip()
            if 'rel="next"' in part:
                match = re.search(r"<([^>]+)>", part)
                if match:
                    next_url = match.group(1)
                    break
        url = next_url
        params = None  # next_url include deja toți parametrii
        time.sleep(SHOPIFY_RATE_DELAY)

    log.info(f"  → {len(barcode_to_inv_item)} variante cu barcode găsite")
    return barcode_to_inv_item


def shopify_get_location_id() -> int | None:
    """Returnează primul location_id dacă nu e setat manual în .env."""
    if SHOPIFY_LOCATION_ID:
        return int(SHOPIFY_LOCATION_ID)

    data = shopify_get("locations.json")
    if not data:
        return None
    locations = data.get("locations", [])
    if not locations:
        log.error("Shopify: nicio locație găsită.")
        return None
    loc_id = locations[0]["id"]
    log.info(f"  Shopify: folosesc locația '{locations[0]['name']}' (ID: {loc_id})")
    if len(locations) > 1:
        log.warning(f"  Shopify: există {len(locations)} locații — setează SHOPIFY_LOCATION_ID în .env dacă e greșit")
    return loc_id


def shopify_sync_stock(stock_by_ean: dict[str, int], dry_run=False) -> dict:
    """Actualizează inventory_levels pe Shopify pentru toate variantele cu EAN din fișierul de stoc."""
    if not SHOPIFY_SHOP or not SHOPIFY_ACCESS_TOKEN:
        log.warning("Shopify: credențiale lipsă (SHOPIFY_SHOP / SHOPIFY_ACCESS_TOKEN). Sar peste.")
        return {"skipped": True}

    location_id = shopify_get_location_id()
    if not location_id:
        log.error("Shopify: nu am putut determina location_id. Abort.")
        return {"error": "no_location_id"}

    barcode_map = shopify_get_barcode_map()
    if not barcode_map:
        log.warning("Shopify: nicio variantă cu barcode găsită.")
        return {"updated": 0, "not_found": 0}

    updated = 0
    not_found = 0
    errors = 0

    for ean, qty in stock_by_ean.items():
        inv_item_id = barcode_map.get(ean)
        if inv_item_id is None:
            not_found += 1
            log.debug(f"  Shopify: EAN {ean} nu există în magazin — ignorat")
            continue

        result = shopify_post("inventory_levels/set.json", {
            "location_id":        location_id,
            "inventory_item_id":  inv_item_id,
            "available":          qty,
        }, dry_run=dry_run)

        if result is not None:
            updated += 1
            log.debug(f"  Shopify: EAN {ean} → {qty} buc OK")
        else:
            errors += 1
            log.error(f"  Shopify: eroare la actualizarea EAN {ean}")

        time.sleep(SHOPIFY_RATE_DELAY)

    log.info(f"Shopify: actualizat={updated}, negăsite={not_found}, erori={errors}")
    return {"updated": updated, "not_found": not_found, "errors": errors}

# ── orchestrator ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sincronizare stocuri ERP → eMAG + Shopify")
    parser.add_argument("filepath",        nargs="?",       help="Cale fișier stoc .xls (opțional)")
    parser.add_argument("--only-emag",     action="store_true")
    parser.add_argument("--only-shopify",  action="store_true")
    parser.add_argument("--dry-run",       action="store_true", help="Simulare fără modificări reale")
    args = parser.parse_args()

    run_emag    = not args.only_shopify
    run_shopify = not args.only_emag

    if args.dry_run:
        log.info("═══ DRY-RUN: nicio modificare reală nu va fi trimisă ═══")

    log.info("══════════════════════════════════════════")
    log.info(f"  Sync stoc — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("══════════════════════════════════════════")

    # 1. Găsesc fișierul stoc
    if args.filepath:
        filepath = args.filepath
        file_date = date.today()
    else:
        result = find_latest_stoc_file()
        if result is None:
            log.error("Nu am găsit niciun fișier stoc în docs_input/. Abort.")
            sys.exit(1)
        file_date, filepath = result
        log.info(f"Fișier stoc detectat: {filepath}  (data: {file_date})")

    # 2. Citesc și agreghez stocul pe EAN
    stock_by_ean = read_stock_by_ean(filepath)
    if not stock_by_ean:
        log.error("Niciun stoc citit. Abort.")
        sys.exit(1)

    results = {"file": filepath, "ean_count": len(stock_by_ean)}

    # 3. eMAG
    if run_emag:
        log.info("─── eMAG ─────────────────────────────────")
        emag_result = emag_sync_stock(stock_by_ean, dry_run=args.dry_run)
        results["emag"] = emag_result

    # 4. Shopify
    if run_shopify:
        log.info("─── Shopify ───────────────────────────────")
        shopify_result = shopify_sync_stock(stock_by_ean, dry_run=args.dry_run)
        results["shopify"] = shopify_result

    # 5. Sumar
    log.info("══════════════════════════════════════════")
    log.info("SUMAR:")
    log.info(f"  EAN-uri în fișier stoc:  {results['ean_count']}")
    if "emag" in results:
        r = results["emag"]
        if r.get("skipped"):
            log.info("  eMAG:    credențiale lipsă — sărit")
        else:
            log.info(f"  eMAG:    actualizat={r.get('updated',0)}, "
                     f"negăsite={r.get('not_found',0)}, erori={r.get('errors',0)}")
    if "shopify" in results:
        r = results["shopify"]
        if r.get("skipped"):
            log.info("  Shopify: credențiale lipsă — sărit")
        else:
            log.info(f"  Shopify: actualizat={r.get('updated',0)}, "
                     f"negăsite={r.get('not_found',0)}, erori={r.get('errors',0)}")
    log.info("══════════════════════════════════════════")


if __name__ == "__main__":
    main()
