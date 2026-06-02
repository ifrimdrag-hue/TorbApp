"""
Import comenzi Leonex în tranzit din Order Form .xls.

Format așteptat: Sheet 'Sheet1' cu date de la rândul 3 (index 0).
Coloane:
  [0] Nr.              → (ignorat)
  [1] Cod produs       → cod_furnizor (ex: MK001730)
  [2] Descriere        → descriere
  [3] Pieces/box       → units_per_carton
  [4] Boxes/pallet     → (informativ)
  [5] Nr. of pieces    → cantitate_comandata (total bucăți)
  [6] Value/piece      → pret_valuta (EUR)
  [7] Total value      → total_valuta
  [8] Pallets          → cantitate_baxuri

Rândurile cu cantitate = 0 sunt sărite (produse necomandante în acest order).
SKU-ul este mapat din cod_furnizor (ex: MK001730) prin stoc/tranzactii.
Data comenzii extrasă din numele fișierului (ex: Order 92 from 27.05.2026 ipek.xls → 2026-05-27).

Usage:
    python import_comenzi_tranzit_leonex.py [<cale_fisier.xls>] [--eta YYYY-MM-DD] [--force]
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
DEFAULT_DIR = "docs_input/comenzi Leonex"
DATA_START  = 3   # rând 0-indexed unde încep datele (după header)
COL_REF     = 1
COL_DESC    = 2
COL_PCS_BOX = 3
COL_QTY_PCS = 5
COL_PRICE   = 6
COL_TOTAL   = 7
COL_PALLETS = 8


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


def parse_order_date(filename):
    """Order 92 from 27.05.2026 ipek.xls → 2026-05-27"""
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


def map_leonex_ref_to_sku(conn, ref):
    """Mapează codul Leonex (ex: MK001730) la SKU din stoc/tranzactii."""
    if not ref:
        return None
    # 1) Match exact pe stoc.cod_mare
    row = conn.execute(
        "SELECT sku FROM stoc WHERE cod_mare = ? ORDER BY data_snapshot DESC LIMIT 1",
        (ref,)
    ).fetchone()
    if row:
        return row[0]
    # 2) Match pe stoc.cod_produs sau sku conținând ref
    row = conn.execute(
        "SELECT sku FROM stoc WHERE cod_produs = ? OR sku LIKE ? "
        "ORDER BY data_snapshot DESC LIMIT 1",
        (ref, f"%{ref}%")
    ).fetchone()
    if row:
        return row[0]
    # 3) Fallback în tranzactii
    row = conn.execute(
        "SELECT DISTINCT sku FROM tranzactii "
        "WHERE cod_produs = ? OR sku LIKE ? "
        "ORDER BY LENGTH(sku) LIMIT 1",
        (ref, f"%{ref}%")
    ).fetchone()
    return row[0] if row else None


def read_order_lines(filepath):
    print(f"  Citesc: {filepath}")
    book = xlrd.open_workbook(filepath)

    # Caută primul sheet cu date
    ws = None
    for sh in book.sheets():
        if sh.nrows > DATA_START:
            ws = sh
            break
    if ws is None:
        print(f"    ! Niciun sheet cu date găsit. Sheets: {book.sheet_names()}")
        return []

    lines = []
    for r in range(DATA_START, ws.nrows):
        qty_pcs = num(ws.cell_value(r, COL_QTY_PCS))
        if not qty_pcs or qty_pcs <= 0:
            continue
        ref = s(ws.cell_value(r, COL_REF))
        if not ref:
            continue

        descriere   = s(ws.cell_value(r, COL_DESC))
        units_box   = int(num(ws.cell_value(r, COL_PCS_BOX), 0) or 0) or None
        pallets     = num(ws.cell_value(r, COL_PALLETS))
        unit_price  = num(ws.cell_value(r, COL_PRICE))
        total       = num(ws.cell_value(r, COL_TOTAL))

        # Recalculează totalul dacă lipsește sau e 0
        if not total and unit_price and qty_pcs:
            total = round(unit_price * qty_pcs, 2)

        lines.append({
            "cod_furnizor":        ref,
            "descriere":           descriere,
            "units_per_carton":    units_box,
            "cantitate_baxuri":    int(pallets) if pallets else None,
            "cantitate_comandata": int(qty_pcs),
            "pret_valuta":         unit_price,
            "total_valuta":        round(total, 2) if total else None,
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
            eta = (base + timedelta(days=lead_time_days(conn, "Leonex"))).isoformat()

        order_no   = os.path.splitext(file_src)[0]
        total_eur  = round(sum(line.get("total_valuta") or 0 for line in lines), 2)

        if existing and force:
            print(f"    --force: șterg comanda existentă id={existing[0]}")
            conn.execute("DELETE FROM comenzi_furnizori_linii WHERE comanda_id = ?", (existing[0],))
            conn.execute("DELETE FROM comenzi_furnizori WHERE id = ?", (existing[0],))

        cur = conn.execute("""
            INSERT INTO comenzi_furnizori
                (nr_comanda, furnizor, data_comanda, data_estimata_livrare, eta,
                 status, file_source, total_usd, moneda, observatii)
            VALUES (?, 'Leonex', COALESCE(?, date('now')), ?, ?,
                    'in_tranzit', ?, ?, 'EUR', ?)
        """, (order_no, order_date, eta, eta, file_src, total_eur,
              f"Importat din {file_src} | În tranzit | ETA {eta}"))
        comanda_id = cur.lastrowid

        inserted   = 0
        unmatched  = 0
        unmatched_refs = []
        for line in lines:
            sku = map_leonex_ref_to_sku(conn, line["cod_furnizor"])
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
            print(f"    Refs nemapate: {unmatched_refs}")
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
