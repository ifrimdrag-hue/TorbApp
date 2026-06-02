"""Parser pentru raportul intern de stocuri.

Citeste un .xls/.xlsx, extrage coloanele relevante (cod, codmare, codbare, cantit),
deduplicates pe SKU si suma cantitatile pe loturi.
"""

from io import BytesIO
from typing import NamedTuple
import pandas as pd

from .report_columns import COLUMN_SKU, COLUMN_CODMARE, COLUMN_EAN, COLUMN_QTY


class StockRow(NamedTuple):
    sku: str                    # cod intern (ex: "712", "1413")
    codmare: str | None         # cod alternativ pt match Shopify (ex: "71395-00" sau "723")
    ean: str | None             # codbare pt match eMAG (ex: "4792252933125")
    qty: int                    # cantitate totala (sumata pe loturi)


class ParseResult(NamedTuple):
    rows: list[StockRow]
    warnings: list[str]
    total_rows_in_file: int
    duplicates_summed: int


def _to_clean_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    return "" if s.lower() == "nan" else s


def _to_codmare(value) -> str | None:
    """codmare vine fie ca int (3-digit), fie ca string '71395-00'. Normalizam la string."""
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        if value.is_integer():
            return str(int(value))
    s = str(value).strip().lstrip("'")
    if not s or s.lower() == "nan":
        return None
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _to_ean_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        if pd.isna(value):
            return None
        if value.is_integer():
            return str(int(value))
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _to_int(value) -> int | None:
    s = _to_clean_str(value)
    if not s:
        return None
    try:
        return int(float(s.replace(",", ".")))
    except ValueError:
        return None


def parse_excel(content: bytes) -> ParseResult:
    df = pd.read_excel(BytesIO(content), dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    total = len(df)

    col_lookup = {c.lower(): c for c in df.columns}
    required = {
        "SKU": COLUMN_SKU,
        "Codmare": COLUMN_CODMARE,
        "EAN": COLUMN_EAN,
        "Cantitate": COLUMN_QTY,
    }
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for label, expected in required.items():
        actual = col_lookup.get(expected.lower())
        if actual is None:
            missing.append(f"{label} (cautat ca '{expected}')")
        else:
            resolved[label] = actual

    if missing:
        raise ValueError(
            "Lipsesc coloane in Excel: "
            + ", ".join(missing)
            + ". Coloane gasite: "
            + ", ".join(df.columns)
        )

    warnings: list[str] = []
    accumulator: dict[str, StockRow] = {}
    duplicates_summed = 0

    for idx, row in df.iterrows():
        excel_row = idx + 2
        sku = _to_clean_str(row[resolved["SKU"]])
        if not sku:
            continue

        codmare = _to_codmare(row[resolved["Codmare"]])
        ean = _to_ean_str(row[resolved["EAN"]])
        qty = _to_int(row[resolved["Cantitate"]])

        if qty is None:
            warnings.append(f"Rand {excel_row} (SKU {sku}): cantitate invalida, ignorat")
            continue
        if qty < 0:
            warnings.append(f"Rand {excel_row} (SKU {sku}): cantitate negativa {qty}, transformat in 0")
            qty = 0

        if sku in accumulator:
            prev = accumulator[sku]
            accumulator[sku] = StockRow(
                sku=sku,
                codmare=prev.codmare or codmare,
                ean=prev.ean or ean,
                qty=prev.qty + qty,
            )
            duplicates_summed += 1
        else:
            accumulator[sku] = StockRow(sku=sku, codmare=codmare, ean=ean, qty=qty)

    return ParseResult(
        rows=list(accumulator.values()),
        warnings=warnings,
        total_rows_in_file=total,
        duplicates_summed=duplicates_summed,
    )
