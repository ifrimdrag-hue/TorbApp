"""
Import comenzi Toras în tranzit din Order Form .xls.

Format așteptat: Sheet 'CHOCOLATES TORRAS ' cu date de la rândul 11.
Coloane:
  [1] REF                 → cod_furnizor (ex: 569, 524, 0401)
  [2] Description         → descriere
  [3] Weight              → (anexat la descriere)
  [4] Unit price EUR      → pret_valuta
  [5] Units per carton    → units_per_carton
  [9] Order in cartons    → cantitate_baxuri

Maparea code→sku: caută SKU care conține '-{code}' (ex: cod 569 → SKU
'T.CIOC ALBA CU FRUCTE GOJI 75GR-569 (...)').

Status implicit: 'in_tranzit'. Data comandă din numele fișierului
(ORDER Toras14.04.2026.xls → 2026-04-14). Data estimată livrare = arg
opțional --eta YYYY-MM-DD sau data_comanda + lead_time Toras.

Usage:
    python import_comenzi_tranzit_toras.py [<cale_fisier.xls>] [--eta 2026-05-14] [--force]
"""

import sys
import os
import re
import sqlite3
import xlrd
from datetime import date, datetime, timedelta

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH     = "data/torb.db"
DEFAULT_DIR = "docs_input/comenzi Toras"
SHEET_NAME  = "CHOCOLATES TORRAS "
DATA_START  = 11
COL_REF        = 1
COL_DESC       = 2
COL_WEIGHT     = 3
COL_PRICE      = 4
COL_UNITS_CTN  = 5
COL_QTY_CTN    = 9


def num(v, default=None):
    if v in (None, ""):
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def s(v):
    if v is None:
        return None
    if isinstance(v, float) and v == int(v):
        v = int(v)
    x = str(v).strip()
    return x if x else None


def normalize_ref(v):
    """Toras refs come as floats (569.0), ints (569) or strings ('0401').
    Normalize to compact string preserving leading zeros for non-numeric."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        return v.strip() or None
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return str(v)
    return str(v).strip() or None


def parse_order_date(filename):
    """ORDER Toras14.04.2026.xls → 2026-04-14"""
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", filename)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return None


def lead_time_days(conn, furnizor):
    cur = conn.execute(
        "SELECT zile_livrare FROM termene_aprovizionare WHERE furnizor = ?",
        (furnizor,)
    )
    row = cur.fetchone()
    return row[0] if row else 45


def map_toras_ref_to_sku(conn, ref):
    """ref '569' → SKU conținând '-569' (ex: 'T.CIOC ALBA ... 75GR-569 (...)').

    Caută întâi în stoc (mai sigur — match pe cod_mare exact și apoi pe sku),
    fallback pe tranzactii. Fără filtru de furnizor, ca să nu pierdem SKU-uri
    care au fost (eronat) tag-uite Altele în istoric."""
    if not ref:
        return None
    needle = f"-{ref}"
    # 1) Match exact pe stoc.cod_mare (când ref vine ca '0401' sau '569')
    row = conn.execute(
        "SELECT sku FROM stoc WHERE cod_mare = ? "
        "ORDER BY data_snapshot DESC LIMIT 1", (ref,)
    ).fetchone()
    if row:
        return row[0]
    # 2) Match pe sku/cod_mare cu '-{ref}' delimitat (în stoc, fără filtru furnizor)
    row = conn.execute("""
        SELECT sku FROM stoc
        WHERE (sku LIKE ? OR sku LIKE ? OR cod_mare LIKE ? OR cod_mare LIKE ?)
        ORDER BY data_snapshot DESC, LENGTH(sku) LIMIT 1
    """, (f"%{needle} %", f"%{needle}(%", f"%{needle} %", f"%{needle}(%")).fetchone()
    if row:
        return row[0]
    # 3) Fallback substring în stoc
    row = conn.execute(
        "SELECT sku FROM stoc WHERE sku LIKE ? OR cod_mare LIKE ? "
        "ORDER BY data_snapshot DESC, LENGTH(sku) LIMIT 1",
        (f"%{ref}%", f"%{ref}%")
    ).fetchone()
    if row:
        return row[0]
    # 4) Ultim resort: tranzactii (SKU-uri vândute istoric, fără furnizor filter)
    row = conn.execute(
        "SELECT DISTINCT sku FROM tranzactii WHERE sku LIKE ? OR sku LIKE ? "
        "ORDER BY LENGTH(sku) LIMIT 1",
        (f"%{needle} %", f"%{needle}(%")
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "SELECT DISTINCT sku FROM tranzactii WHERE sku LIKE ? "
        "ORDER BY LENGTH(sku) LIMIT 1",
        (f"%{ref}%",)
    ).fetchone()
    return row[0] if row else None


def read_order_lines(filepath):
    print(f"  Citesc: {filepath}")
    book = xlrd.open_workbook(filepath)
    if SHEET_NAME not in book.sheet_names():
        # tolerează spațiu trailing diferit
        candidates = [n for n in book.sheet_names() if n.strip().upper().startswith("CHOCOLATES TORRAS")]
        if not candidates:
            print(f"    ! Sheet-ul Toras nu a fost găsit. Sheets: {book.sheet_names()}")
            return []
        sheet_name = candidates[0]
    else:
        sheet_name = SHEET_NAME

    ws = book.sheet_by_name(sheet_name)
    lines = []
    for r in range(DATA_START, ws.nrows):
        qty_ctn = num(ws.cell_value(r, COL_QTY_CTN))
        if not qty_ctn or qty_ctn <= 0:
            continue
        ref = normalize_ref(ws.cell_value(r, COL_REF))
        if not ref:
            continue

        desc_main = s(ws.cell_value(r, COL_DESC)) or ""
        weight = s(ws.cell_value(r, COL_WEIGHT)) or ""
        descriere = (desc_main + (" " + weight if weight else "")).strip() or None

        units_per_ctn = int(num(ws.cell_value(r, COL_UNITS_CTN), 0) or 0) or None
        cantitate = int(qty_ctn * (units_per_ctn or 1))
        unit_price = num(ws.cell_value(r, COL_PRICE))
        total = round(unit_price * cantitate, 2) if unit_price and cantitate else None

        lines.append({
            "cod_furnizor":        ref,
            "descriere":           descriere,
            "units_per_carton":    units_per_ctn,
            "cantitate_baxuri":    int(qty_ctn),
            "cantitate_comandata": cantitate,
            "pret_valuta":         unit_price,
            "total_valuta":        total,
        })
    print(f"    → {len(lines)} linii cu cantitate > 0")
    return lines


def import_file(filepath, eta=None, force=False):
    conn = sqlite3.connect(DB_PATH)
    try:
        file_src = os.path.basename(filepath)

        cur = conn.execute(
            "SELECT id, status FROM comenzi_furnizori WHERE file_source = ?",
            (file_src,)
        )
        existing = cur.fetchone()
        if existing and not force:
            print(f"  Sar peste: {file_src} — deja importat (id={existing[0]}, status={existing[1]}).")
            print("    Folosește --force ca să suprascrii.")
            return 0

        lines = read_order_lines(filepath)
        if not lines:
            print("    ! Nicio linie — sar peste.")
            return 0

        order_date = parse_order_date(file_src)
        if not eta:
            base = datetime.strptime(order_date, "%Y-%m-%d").date() if order_date \
                   else date.fromtimestamp(os.path.getmtime(filepath))
            eta = (base + timedelta(days=lead_time_days(conn, "Toras"))).isoformat()

        order_no = os.path.splitext(file_src)[0]
        total_eur = round(sum(line.get("total_valuta") or 0 for line in lines), 2)

        if existing and force:
            print(f"    --force: șterg comanda existentă id={existing[0]}")
            conn.execute("DELETE FROM comenzi_furnizori_linii WHERE comanda_id = ?", (existing[0],))
            conn.execute("DELETE FROM comenzi_furnizori WHERE id = ?", (existing[0],))

        cur = conn.execute("""
            INSERT INTO comenzi_furnizori
                (nr_comanda, furnizor, data_comanda, data_estimata_livrare, eta,
                 status, file_source, total_usd, moneda, observatii)
            VALUES (?, 'Toras', COALESCE(?, date('now')), ?, ?,
                    'in_tranzit', ?, ?, 'EUR', ?)
        """, (order_no, order_date, eta, eta, file_src, total_eur,
              f"Importat din {file_src} | În tranzit | ETA {eta}"))
        comanda_id = cur.lastrowid

        inserted = 0
        unmatched = 0
        unmatched_refs = []
        for line in lines:
            sku = map_toras_ref_to_sku(conn, line["cod_furnizor"])
            if not sku:
                sku = line["descriere"] or line["cod_furnizor"]
                unmatched += 1
                unmatched_refs.append(line["cod_furnizor"])
            conn.execute("""
                INSERT INTO comenzi_furnizori_linii
                    (comanda_id, sku, cod_furnizor, descriere,
                     units_per_carton, cantitate_baxuri, cantitate_comandata,
                     pret_valuta, moneda, total_valuta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'EUR', ?)
            """, (
                comanda_id, sku, line["cod_furnizor"], line["descriere"],
                line["units_per_carton"], line["cantitate_baxuri"],
                line["cantitate_comandata"], line["pret_valuta"],
                line["total_valuta"],
            ))
            inserted += 1
        conn.commit()
        print(f"    OK comanda_id={comanda_id} | {inserted} linii ({unmatched} fără mapare SKU) | total {total_eur:,.2f} EUR | ETA {eta}")
        if unmatched_refs:
            print(f"    Refs nemaper: {unmatched_refs}")
        return inserted
    finally:
        conn.close()


def run(filepath=None, eta=None, force=False):
    if filepath:
        return import_file(filepath, eta=eta, force=force)
    if not os.path.isdir(DEFAULT_DIR):
        print(f"EROARE: nu găsesc directorul {DEFAULT_DIR}")
        return 0
    total = 0
    for fname in sorted(os.listdir(DEFAULT_DIR)):
        if fname.lower().endswith((".xls", ".xlsx")) and not fname.startswith("~$"):
            total += import_file(os.path.join(DEFAULT_DIR, fname), eta=eta, force=force)
    return total


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    args = [a for a in args if a != "--force"]

    eta = None
    if "--eta" in args:
        i = args.index("--eta")
        eta = args[i + 1]
        args = args[:i] + args[i + 2:]

    fp = args[0] if args else None
    run(fp, eta=eta, force=force)
