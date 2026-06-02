"""Parser + snapshot pentru fisierul de preturi (PRETURI PRODUSE TOATE!.xlsx).

Fisierul are 7+ sheet-uri (per brand), structura comuna:
  Cod articol, Denumire produs, Cod EAN, Pret unitar (lei) fara TVA, Cota TVA,
  Pret Minim, Pret V (sau Pret), Pret Maxim, Emag, Trendyol, etc.

Numele coloanelor variaza usor intre sheet-uri (Pret Minim vs Pret Minim(20) vs
Pret Minim (20)), deci mapam case-insensitive cu pattern matching.
"""

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import NamedTuple

import pandas as pd


DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
PRICES_SNAPSHOT_FILE = DATA_DIR / "latest_prices_snapshot.json"


class PriceProduct(NamedTuple):
    ean: str | None
    cod_articol: str | None       # acelasi cu codmare (poate avea sufix -00 sau nu)
    name: str
    price_min: float | None
    price_v: float | None         # pret actual / current
    price_max: float | None       # RRP / list price
    vat: float | None             # ex 0.11 sau 0.21
    emag_listed: bool | None
    brand: str                    # numele sheet-ului


class PricesParseResult(NamedTuple):
    products: list[PriceProduct]
    skipped_rows: int
    sheets_processed: list[str]


def _norm_col(c: str) -> str:
    return str(c).strip().lower()


def _find_col(cols_lower: dict[str, str], candidates: list[str]) -> str | None:
    """Cauta o coloana al carei nume normalizat incepe cu unul din candidatii dati."""
    for cand in candidates:
        c = cand.lower().strip()
        # exact match first
        if c in cols_lower:
            return cols_lower[c]
        # prefix match
        for k, v in cols_lower.items():
            if k.startswith(c):
                return v
    return None


def _to_float(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        f = float(str(v).strip().replace(",", "."))
        return f if f >= 0 else None
    except (ValueError, TypeError):
        return None


def _to_str(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip().lstrip("'")


def _parse_emag_flag(v) -> bool | None:
    s = _to_str(v).lower()
    if not s:
        return None
    if s in ("da", "yes", "y", "1", "true"):
        return True
    if s in ("nu", "no", "n", "0", "false"):
        return False
    return None


def parse_prices_xlsx(content: bytes) -> PricesParseResult:
    sheets = pd.read_excel(BytesIO(content), sheet_name=None, dtype=object)
    products: list[PriceProduct] = []
    skipped = 0
    processed: list[str] = []

    for sheet_name, df in sheets.items():
        df.columns = [str(c).strip() for c in df.columns]
        cols_lower = {_norm_col(c): c for c in df.columns}

        c_ean   = _find_col(cols_lower, ["cod ean", "ean"])
        c_cod   = _find_col(cols_lower, ["cod articol"])
        c_name  = _find_col(cols_lower, ["denumire produs", "denumire"])
        c_min   = _find_col(cols_lower, ["pret minim", "pret min"])
        c_v     = _find_col(cols_lower, ["pret v", "pret cu tva", "pret"])
        c_max   = _find_col(cols_lower, ["pret maxim", "pret max"])
        c_vat   = _find_col(cols_lower, ["cota tva", "tva"])
        c_emag  = _find_col(cols_lower, ["emag"])

        if not (c_ean or c_cod):
            continue  # sheet fara coloana cheie — ignoram
        processed.append(sheet_name)

        for _, row in df.iterrows():
            ean = _to_str(row.get(c_ean)) if c_ean else ""
            cod = _to_str(row.get(c_cod)) if c_cod else ""
            name = _to_str(row.get(c_name)) if c_name else ""

            # Skip header-like rows (nu au EAN si nici cod articol — sunt linii de coeficienti)
            if not ean and not cod:
                skipped += 1
                continue

            products.append(PriceProduct(
                ean=ean or None,
                cod_articol=cod or None,
                name=name,
                price_min=_to_float(row.get(c_min)) if c_min else None,
                price_v=_to_float(row.get(c_v)) if c_v else None,
                price_max=_to_float(row.get(c_max)) if c_max else None,
                vat=_to_float(row.get(c_vat)) if c_vat else None,
                emag_listed=_parse_emag_flag(row.get(c_emag)) if c_emag else None,
                brand=sheet_name,
            ))

    return PricesParseResult(products=products, skipped_rows=skipped, sheets_processed=processed)


def save_snapshot(parsed: PricesParseResult, source_filename: str = "") -> None:
    data = {
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "source_filename": source_filename,
        "sheets_processed": parsed.sheets_processed,
        "skipped_rows": parsed.skipped_rows,
        "products": [
            {
                "ean": p.ean,
                "cod_articol": p.cod_articol,
                "name": p.name,
                "price_min": p.price_min,
                "price_v": p.price_v,
                "price_max": p.price_max,
                "vat": p.vat,
                "emag_listed": p.emag_listed,
                "brand": p.brand,
            }
            for p in parsed.products
        ],
    }
    PRICES_SNAPSHOT_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_snapshot() -> dict | None:
    if not PRICES_SNAPSHOT_FILE.exists():
        return None
    return json.loads(PRICES_SNAPSHOT_FILE.read_text(encoding="utf-8"))


def normalize_match_key(value) -> str | None:
    """Aceeasi normalizare ca in stocuri_shopify (-XX strip + apostrof)."""
    if value is None:
        return None
    s = str(value).strip().lstrip("'")
    if "-" in s:
        parts = s.rsplit("-", 1)
        if parts[1].isdigit() and len(parts[1]) <= 3:
            s = parts[0]
    return s.strip() or None


def build_lookup(snapshot: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    """Construieste 2 lookup-uri: dupa EAN si dupa cod_articol normalizat."""
    by_ean: dict[str, dict] = {}
    by_cod: dict[str, dict] = {}
    for p in snapshot.get("products", []):
        if p.get("ean"):
            by_ean[p["ean"]] = p
        cod_norm = normalize_match_key(p.get("cod_articol"))
        if cod_norm:
            by_cod[cod_norm] = p
    return by_ean, by_cod
