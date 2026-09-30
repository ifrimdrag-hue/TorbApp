"""
Import comenzi Celmar în tranzit din Order Form .xls.

Coloanele se găsesc după textul din antet (rândul care conține PRODUCT), nu
după poziție: formularul își schimbă layout-ul între versiuni (din aug. 2026 a
dispărut o coloană și 'Order pcs' a ajuns pe indexul fostei 'TOTAL Value').
Antet → câmp:
  PRODUCT                       → descriere (cuvânt RO în majuscule la final)
  ...Price / pcs (PLN)          → pret_valuta
  pcs / pallet                  → pcs_per_pallet (3600 = 20 pcs/cutie, 1080 = 80 pcs/cutie)
  Order Pallets / New order pal → cantitate_baxuri (paleți)
  Order pcs                     → cantitate_comandata
Fără PRODUCT sau Order pcs în antet, importul se oprește cu eroare.

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
HEADER_SCAN_ROWS = 20   # the PRODUCT header row is searched for in the first N rows
REQUIRED_COLS = {"product": "PRODUCT", "qty_pcs": "Order pcs"}

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


def _norm(v):
    return " ".join(str(v or "").replace("\xa0", " ").split()).lower()


def column_role(header):
    """Logical field of one Order Form header cell, or None.

    Keyword match, not exact text: the supplier rewords and misspells headers
    between versions ('pcs / pallet' vs 'pcs / plallet', 'New order pal' vs
    'Order Pallets'). 'price' is tested before 'pcs' because the price header
    also contains 'pcs'."""
    h = _norm(header)
    if h.startswith("product"):
        return "product"
    if "price" in h:
        return "price"
    if "pcs" in h:
        return "qty_pcs" if "order" in h else "pcs_per_pallet"
    if "order" in h and "pal" in h:
        return "qty_pal"
    return None


def detect_columns(ws):
    """(header_row, {role: [cols]}) for the first row holding a PRODUCT header,
    or (None, {}) if there is none."""
    for r in range(min(ws.nrows, HEADER_SCAN_ROWS)):
        roles = [column_role(ws.cell_value(r, c)) for c in range(ws.ncols)]
        if "product" in roles:
            cols = {}
            for c, role in enumerate(roles):
                if role:
                    cols.setdefault(role, []).append(c)
            return r, cols
    return None, {}


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


def parse_order_sheet(ws):
    """Order lines with a quantity > 0. Raises ValueError when the header row or
    a required column is missing, or the quantity column is ambiguous, so a new
    layout fails loudly instead of importing another column as the quantity."""
    header_row, cols = detect_columns(ws)
    if header_row is None:
        raise ValueError("nu găsesc rândul de antet cu PRODUCT")
    missing = [label for role, label in REQUIRED_COLS.items() if role not in cols]
    if missing:
        raise ValueError(f"lipsește coloana {', '.join(missing)} din antet")
    if len(cols["qty_pcs"]) > 1:
        raise ValueError("antetul are mai multe coloane de cantitate (Order pcs)")

    def cell(r, role):
        return ws.cell_value(r, cols[role][0]) if role in cols else None

    lines = []
    for r in range(header_row + 1, ws.nrows):
        qty_pcs = num(cell(r, "qty_pcs"))
        if not qty_pcs or qty_pcs <= 0:
            continue
        product = s(cell(r, "product"))
        if not product:
            continue

        pcs_per_pal = num(cell(r, "pcs_per_pallet"))
        qty_pal = num(cell(r, "qty_pal"))
        price = num(cell(r, "price"))
        total = round(price * qty_pcs, 2) if price else None

        lines.append({
            'descriere':            product,
            'pcs_per_pallet':       int(pcs_per_pal) if pcs_per_pal else None,
            'cantitate_baxuri':     round(qty_pal, 4) if qty_pal else None,
            'cantitate_comandata':  int(round(qty_pcs)),
            'pret_valuta':          price,
            'total_valuta':         total,
        })
    return lines


def read_order_lines(filepath):
    print(f"  Citesc: {filepath}")
    sheets = xlrd.open_workbook(filepath).sheets()
    ws = next((sh for sh in sheets if set(REQUIRED_COLS) <= set(detect_columns(sh)[1])), sheets[0])
    lines = parse_order_sheet(ws)
    print(f"    → {len(lines)} linii cu cantitate > 0")
    return lines, parse_title_date(ws)


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
    try:
        run(fp, force=force)
    except ValueError as exc:
        print(f"EROARE: format necunoscut al comenzii Celmar — {exc}")
        sys.exit(1)
