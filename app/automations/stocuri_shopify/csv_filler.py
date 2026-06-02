"""Genereaza CSV-ul Shopify Inventory cu cantitatile actualizate.

Flow:
  1. Citim Inventory CSV exportat din Shopify (Products -> Inventory -> Export -> Plain CSV)
  2. Pentru fiecare rand cu Location = ACTIVE_LOCATION:
     - Daca SKU-ul exista in stocks_by_sku → scriem cantitatea in coloana 'On hand (new)'
     - Daca nu → scriem 0 (produs scos din raport)
  3. Randurile pentru alte locatii (TORB LOGISTIC etc.) raman neatinse.
"""

from io import StringIO
from typing import NamedTuple
import csv


# Locatia activa pe Shopify (cea pe care o updatam). Restul (ex: TORB LOGISTIC) au "not stocked".
ACTIVE_LOCATION = "Shop location"

SKU_COL = "SKU"
LOCATION_COL = "Location"
ON_HAND_NEW_COL = "On hand (new)"


class CsvFillResult(NamedTuple):
    file_bytes: bytes
    matched: int                  # SKU-uri Shopify pentru care am scris cantitate (din raport)
    set_to_zero: int              # SKU-uri Shopify fara match -> set la 0
    rows_other_location: int      # randuri pe alte locatii (neatinse)
    matched_skus: set[str]


def _normalize_sku(value) -> str | None:
    """Normalizare unitara SKU: strip apostrof Excel + strip sufix '-XX'.

    Aceeasi normalizare se aplica in ambele directii (Shopify SKU si codmare din raport)
    ca sa prindem cazuri precum:
      - Shopify "'72143-00" + raport codmare "72143-00" → ambele "72143"
      - Shopify "70401" + raport codmare "70401-00" → ambele "70401"
      - Shopify "'90204" + raport codmare "90204" → ambele "90204"
    """
    if value is None:
        return None
    s = str(value).strip().lstrip("'")
    # Strip trailing -XX (max 3 cifre) — pattern eMAG/intern
    if "-" in s:
        parts = s.rsplit("-", 1)
        if parts[1].isdigit() and len(parts[1]) <= 3:
            s = parts[0]
    return s.strip() or None


def fill_inventory_csv(csv_bytes: bytes, stocks_by_sku: dict[str, int]) -> CsvFillResult:
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(StringIO(text))
    fieldnames = reader.fieldnames or []

    if SKU_COL not in fieldnames:
        raise ValueError(
            f"CSV-ul Shopify nu are coloana '{SKU_COL}'. Coloane gasite: {', '.join(fieldnames)}"
        )
    if LOCATION_COL not in fieldnames:
        raise ValueError(f"CSV-ul Shopify nu are coloana '{LOCATION_COL}'.")
    if ON_HAND_NEW_COL not in fieldnames:
        raise ValueError(f"CSV-ul Shopify nu are coloana '{ON_HAND_NEW_COL}'.")

    matched = 0
    set_to_zero = 0
    rows_other_location = 0
    matched_skus: set[str] = set()
    out_rows: list[dict] = []

    for row in reader:
        location = (row.get(LOCATION_COL) or "").strip()
        if location != ACTIVE_LOCATION:
            rows_other_location += 1
            out_rows.append(row)
            continue

        sku = _normalize_sku(row.get(SKU_COL))
        if not sku:
            out_rows.append(row)
            continue

        qty = stocks_by_sku.get(sku)
        if qty is None:
            row[ON_HAND_NEW_COL] = "0"
            set_to_zero += 1
        else:
            row[ON_HAND_NEW_COL] = str(int(qty))
            matched += 1
            matched_skus.add(sku)

        out_rows.append(row)

    out = StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out_rows)

    return CsvFillResult(
        file_bytes=out.getvalue().encode("utf-8-sig"),
        matched=matched,
        set_to_zero=set_to_zero,
        rows_other_location=rows_other_location,
        matched_skus=matched_skus,
    )
