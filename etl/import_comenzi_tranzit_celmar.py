"""
Import comenzi Celmar în tranzit din Order Form .xls.

Format așteptat: Sheet 'Sheet1', header pe rândul 5 (index 5), date de la 6.
Coloane:
  [0] PRODUCT        → descriere (conține cuvânt RO în majuscule la final)
  [1] Price/pcs PLN  → pret_valuta
  [2] pcs / pallet   → pcs_per_pallet (3600 = 20 pcs/cutie, 1080 = 80 pcs/cutie)
  [4] New order pal  → cantitate_baxuri (paleți)
  [5] Order pcs      → cantitate_comandata

Maparea produs→SKU: extrage cuvântul românesc (MUSETEL, SUNATOARE etc.) și
caută 'CELMAR {keyword}' în stoc. Variantele cu pcs_per_pallet ≤ 1200
(80 plicuri) preferă SKU-ul cu '80 PLICURI'.

Usage:
    python import_comenzi_tranzit_celmar.py [<cale_fisier.xls>] [--force]
    # fără argumente: importă tot din docs_input/comenzi Celmar/
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
DEFAULT_DIR = "docs_input/comenzi Celmar"
SHEET_NAME  = "Sheet1"
HEADER_ROW  = 5
DATA_START  = 6
COL_PRODUCT  = 0
COL_PRICE    = 1
COL_PCS_PAL  = 2
COL_PAL_NEW  = 4
COL_QTY_PCS  = 5

# Month names EN → number for title-row date parsing
_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


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
    x = str(v).replace('\xa0', ' ').strip()
    return x if x else None


def extract_romanian_keyword(product_name):
    """'Chamomile (1.5g x 20)      MUSETEL' → 'MUSETEL'
       'Linden with Lemon (1.8 X 20)   TEI CU LAMAIE' → 'TEI CU LAMAIE'
    """
    if not product_name:
        return None
    name = product_name.replace('\xa0', ' ').strip()
    m = re.search(r'\s{2,}([A-ZĂÂÎȘȚŞŢ][A-ZĂÂÎȘȚŞŢ\s]+)$', name)
    if m:
        return m.group(1).strip()
    return None


def parse_title_date(ws):
    """Tries to extract a date from the title cell (row 2).
    'ORDER 28/18 may 2026' → looks for day+month+year pattern."""
    title = s(ws.cell_value(2, 0)) or ''
    m = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{4})',
                  title, re.IGNORECASE)
    if m:
        day, mon, year = m.groups()
        mo = _MONTHS.get(mon[:3].lower())
        if mo:
            try:
                return date(int(year), mo, int(day)).isoformat()
            except ValueError:
                pass
    return None


def parse_filename_date(filename):
    m = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', filename)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return None


def lead_time_days(conn):
    row = conn.execute(
        "SELECT zile_livrare FROM termene_aprovizionare WHERE furnizor = 'Celmar'"
    ).fetchone()
    return row[0] if row else 30


def map_celmar_to_sku(conn, product_name, pcs_per_pallet):
    keyword = extract_romanian_keyword(product_name)
    if not keyword:
        return None
    is_80 = pcs_per_pallet and pcs_per_pallet <= 1200
    if is_80:
        row = conn.execute(
            "SELECT sku FROM stoc WHERE sku LIKE ? "
            "ORDER BY data_snapshot DESC LIMIT 1",
            (f"CELMAR {keyword} 80%",)
        ).fetchone()
        if row:
            return row[0]
    else:
        row = conn.execute(
            "SELECT sku FROM stoc WHERE sku LIKE ? AND sku NOT LIKE '%80 PLICURI%' "
            "ORDER BY LENGTH(sku), data_snapshot DESC LIMIT 1",
            (f"CELMAR {keyword}%",)
        ).fetchone()
        if row:
            return row[0]
    # Fallback: orice match cu keyword
    row = conn.execute(
        "SELECT sku FROM stoc WHERE sku LIKE ? "
        "ORDER BY LENGTH(sku), data_snapshot DESC LIMIT 1",
        (f"CELMAR {keyword}%",)
    ).fetchone()
    return row[0] if row else None


def read_order_lines(filepath):
    print(f"  Citesc: {filepath}")
    book = xlrd.open_workbook(filepath)
    candidates = [n for n in book.sheet_names() if 'sheet' in n.lower() or 'order' in n.lower()]
    sheet_name = SHEET_NAME if SHEET_NAME in book.sheet_names() else (candidates[0] if candidates else book.sheet_names()[0])
    ws = book.sheet_by_name(sheet_name)

    lines = []
    order_date_from_sheet = parse_title_date(ws)
    for r in range(DATA_START, ws.nrows):
        qty_pcs = num(ws.cell_value(r, COL_QTY_PCS))
        if not qty_pcs or qty_pcs <= 0:
            continue
        product = s(ws.cell_value(r, COL_PRODUCT))
        if not product:
            continue

        pcs_per_pal = num(ws.cell_value(r, COL_PCS_PAL))
        qty_pal = num(ws.cell_value(r, COL_PAL_NEW))
        price = num(ws.cell_value(r, COL_PRICE))
        total = round(price * qty_pcs, 2) if price and qty_pcs else None

        lines.append({
            'descriere':            product,
            'pcs_per_pallet':       int(pcs_per_pal) if pcs_per_pal else None,
            'cantitate_baxuri':     round(qty_pal, 4) if qty_pal else None,
            'cantitate_comandata':  int(qty_pcs),
            'pret_valuta':          price,
            'total_valuta':         total,
        })

    print(f"    → {len(lines)} linii cu cantitate > 0")
    return lines, order_date_from_sheet


def import_file(filepath, force=False):
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

        lines, order_date_sheet = read_order_lines(filepath)
        if not lines:
            print("    ! Nicio linie — sar peste.")
            return 0

        order_date = order_date_sheet or parse_filename_date(file_src)
        file_mtime = date.fromtimestamp(os.path.getmtime(filepath))
        lead = lead_time_days(conn)
        base = datetime.strptime(order_date, "%Y-%m-%d").date() if order_date else file_mtime
        eta = (base + timedelta(days=lead)).isoformat()
        order_no = os.path.splitext(file_src)[0]
        total_pln = round(sum(line.get('total_valuta') or 0 for line in lines), 2)

        if existing and force:
            print(f"    --force: șterg comanda existentă id={existing[0]}")
            conn.execute("DELETE FROM comenzi_furnizori_linii WHERE comanda_id = ?", (existing[0],))
            conn.execute("DELETE FROM comenzi_furnizori WHERE id = ?", (existing[0],))

        cur = conn.execute("""
            INSERT INTO comenzi_furnizori
                (nr_comanda, furnizor, data_comanda, data_estimata_livrare, eta,
                 status, file_source, total_usd, moneda, observatii)
            VALUES (?, 'Celmar', COALESCE(?, date('now')), ?, ?,
                    'in_tranzit', ?, ?, 'PLN', ?)
        """, (order_no, order_date, eta, eta, file_src, total_pln,
              f"Importat din {file_src} | În tranzit | ETA {eta} (+{lead}z lead time)"))
        comanda_id = cur.lastrowid

        inserted = 0
        unmatched = 0
        for line in lines:
            sku = map_celmar_to_sku(conn, line['descriere'], line['pcs_per_pallet'])
            if not sku:
                sku = line['descriere']
                unmatched += 1
            conn.execute("""
                INSERT INTO comenzi_furnizori_linii
                    (comanda_id, sku, descriere,
                     units_per_carton, cantitate_baxuri, cantitate_comandata,
                     pret_valuta, moneda, total_valuta)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PLN', ?)
            """, (
                comanda_id, sku, line['descriere'],
                line['pcs_per_pallet'], line['cantitate_baxuri'],
                line['cantitate_comandata'], line['pret_valuta'],
                line['total_valuta'],
            ))
            inserted += 1
        conn.commit()
        print(f"    OK comanda_id={comanda_id} | {inserted} linii ({unmatched} fără mapare SKU) | total {total_pln:,.2f} PLN | ETA {eta}")
        return inserted
    finally:
        conn.close()


def run(filepath=None, force=False):
    if filepath:
        return import_file(filepath, force=force)
    if not os.path.isdir(DEFAULT_DIR):
        print(f"EROARE: nu găsesc directorul {DEFAULT_DIR}")
        return 0
    total = 0
    for fname in sorted(os.listdir(DEFAULT_DIR)):
        if fname.lower().endswith(('.xls', '.xlsx')) and not fname.startswith('~$'):
            total += import_file(os.path.join(DEFAULT_DIR, fname), force=force)
    return total


if __name__ == "__main__":
    args = sys.argv[1:]
    force = '--force' in args
    args = [a for a in args if a != '--force']
    fp = args[0] if args else None
    run(fp, force=force)
