"""
Import comenzi Basilur in tranzit din Order Form .xls (PFI / Proforma).

Format așteptat: Sheet 'Order form' cu header pe rândul 13/14, date de la 15.
Coloane:
  [ 7] CODE                  → cod_furnizor (ex: "70183-00")
  [ 8] PRODUCT DESCRIPTION   → descriere
  [13] Units per Export      → units_per_carton
  [22] Export Ctn CBM
  [26] Weight (Kgs)          → kg/carton
  [30] RO                    → cantitate baxuri pentru RO
  [38] No of Units           → cantitate unitati
  [39] Unit Price US$        → pret unitar
  [40] Total Price US$       → total

Maparea code→sku se face prin căutarea codului în SKU-urile existente
(ex: cod "70197-00" → sku ce conține "70197" în nume).

Status implicit: 'in_tranzit'. Numărul comenzii e derivat din numele fișierului.

Usage:
    python import_comenzi_tranzit_basilur.py [<cale_fisier.xls>]
    # fără argumente: importă tot din docs_input/Comenzi Basilur de sosit/
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

DB_PATH    = "data/torb.db"
DEFAULT_DIR = "docs_input/Comenzi Basilur de sosit"
SHEET_NAME  = "Order form"
HEADER_ROW1 = 13
HEADER_ROW2 = 14
DATA_START  = 15

# Mapping logic name → list of accepted header values for r13 OR r14 (case-
# insensitive, exact match after strip+lower). First match wins. Layout drifts
# between PFI versions (40 vs 46 cols), so locate by header text.
HEADER_LABELS = {
    "code":             ["code"],
    "description":      ["product description"],
    "units_per_export": ["units per export"],
    "cbm":              ["export ctn cbm", "cbm"],
    "ro_cartons":       ["ro"],
    "export_ctns":      ["export ctns", "export ctns."],
    "no_of_units":      ["no of units"],
    "unit_price":       ["unit price us$", "unit price fob us$"],
    "total_price":      ["total price us$", "total price fob us$"],
    "gross_kgs":        ["gross kgs"],
    "net_kgs":          ["nett kgs", "net kgs"],
}


def _norm(v):
    if v is None:
        return ""
    return str(v).strip().lower()


def detect_columns(ws):
    """Return dict logic_name → col_index using exact header text match on
    row 13 or row 14. The first column whose header equals one of the labels
    wins — column indices are NOT compared against each other (so 'code' at
    col 7 doesn't accidentally match the 'codbare' label etc.)."""
    nc = ws.ncols
    h1 = [_norm(ws.cell_value(HEADER_ROW1, c)) for c in range(nc)]
    h2 = [_norm(ws.cell_value(HEADER_ROW2, c)) for c in range(nc)]

    cols = {}
    for logic, labels in HEADER_LABELS.items():
        found = None
        for label in labels:
            for c in range(nc):
                if h1[c] == label or h2[c] == label:
                    found = c
                    break
            if found is not None:
                break
        cols[logic] = found
    return cols


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
    x = str(v).strip()
    return x if x else None


def parse_order_no(filename):
    """Extract order number like 'RO1-004-26' or 'RO1-007-26' from filename."""
    base = os.path.basename(filename)
    m = re.match(r"(RO\d+[\s-]+\d+[\s-]+\d+)", base)
    if m:
        return m.group(1).replace(" ", "").replace("--", "-")
    return os.path.splitext(base)[0]


def parse_pfi_date(filename):
    """Look for 'PFI DD.MM.YYYY' pattern in filename."""
    m = re.search(r"PFI\s+(\d{2})\.(\d{2})\.(\d{4})", filename)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return None


def parse_order_date(filename):
    """Extract any DD.MM.YYYY date from filename (used when no PFI)."""
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", filename)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{mo}-{d}"
    return None


def detect_status(filename):
    """PFI in numele fișierului ⇒ furnizorul a confirmat (in_tranzit).
    Altfel ⇒ comandă trimisă, neconfirmată de furnizor (confirmata)."""
    return "in_tranzit" if "PFI" in filename.upper() else "confirmata"


def lead_time_days(conn, furnizor):
    """Get supplier lead time in days from termene_aprovizionare; default 120 for Basilur."""
    cur = conn.execute(
        "SELECT zile_livrare FROM termene_aprovizionare WHERE furnizor = ?",
        (furnizor,)
    )
    row = cur.fetchone()
    return row[0] if row else 120


def estimate_eta(pfi_date, file_mtime, lead_days):
    """ETA = base_date + lead_days. base_date prefers PFI date, falls back to file mtime."""
    if pfi_date:
        try:
            base = datetime.strptime(pfi_date, "%Y-%m-%d").date()
        except ValueError:
            base = file_mtime
    else:
        base = file_mtime
    return (base + timedelta(days=lead_days)).isoformat()


def map_basilur_code_to_sku(conn, basilur_code):
    """Map e.g. '70183-00' / '80309-00' / '90204-00' → existing SKU.

    Atentie: order form-urile Basilur contin si linii Tipson, KingsLeaf,
    Organsia — toate provin de la acelasi producator si apar pe comenzi comune.
    NU filtram pe furnizor, ca sa prindem si codurile Tipson (80xxx) si
    KingsLeaf (90xxx) prezente pe PFI-ul Basilur.
    """
    if not basilur_code:
        return None
    code = str(basilur_code).strip()
    if not code:
        return None
    # 1. Match exact pe stoc.cod_mare — cel mai sigur (acopera toate brandurile)
    row = conn.execute(
        "SELECT sku FROM stoc WHERE cod_mare = ? "
        "ORDER BY data_snapshot DESC LIMIT 1",
        (code,)
    ).fetchone()
    if row:
        return row[0]
    # 2. Fallback substring pe stoc (fara filtru de furnizor)
    short = code.split("-")[0]
    if not short:
        return None
    row = conn.execute(
        "SELECT sku FROM stoc WHERE cod_mare LIKE ? OR sku LIKE ? LIMIT 1",
        (f"%{short}%", f"%{short}%")
    ).fetchone()
    if row:
        return row[0]
    # 3. Ultim resort: tranzactii (SKU-uri vandute istoric, posibil 0 stoc curent)
    row = conn.execute(
        "SELECT sku FROM tranzactii WHERE sku LIKE ? LIMIT 1",
        (f"%{short}%",)
    ).fetchone()
    return row[0] if row else None


def read_order_lines(filepath):
    print(f"  Citesc: {filepath}")
    book = xlrd.open_workbook(filepath)
    if SHEET_NAME not in book.sheet_names():
        print(f"    ! Sheet '{SHEET_NAME}' lipseste.")
        return []
    ws = book.sheet_by_name(SHEET_NAME)
    ncols = ws.ncols

    cols = detect_columns(ws)
    missing = [k for k in ("code", "ro_cartons", "no_of_units", "unit_price") if cols.get(k) is None]
    if missing:
        print(f"    ! Coloane obligatorii nedetectate: {missing}")
        return []

    def cell(r, name):
        c = cols.get(name)
        if c is None or c >= ncols:
            return None
        return ws.cell_value(r, c)

    lines = []
    for r in range(DATA_START, ws.nrows):
        ro_qty = num(cell(r, "ro_cartons"))
        if not ro_qty or ro_qty <= 0:
            continue

        code = s(cell(r, "code"))
        if not code:
            continue

        lines.append({
            "cod_furnizor":    code,
            "descriere":       s(cell(r, "description")),
            "units_per_carton": int(num(cell(r, "units_per_export"), 0) or 0) or None,
            "cantitate_baxuri": ro_qty,
            "cantitate_comandata": int(num(cell(r, "no_of_units"), 0) or 0),
            "pret_valuta":     num(cell(r, "unit_price")),
            "total_valuta":    num(cell(r, "total_price")),
            "cbm":             num(cell(r, "cbm")),
            "gross_kg":        num(cell(r, "gross_kgs")),
            "net_kg":          num(cell(r, "net_kgs")),
        })

    print(f"    → {len(lines)} linii cu RO > 0")
    return lines


def import_file(filepath, force=False):
    """Import comandă din fișier .xls. `force=True` șterge comanda existentă
    și o reimportă (folosit doar la --force). Default `force=False` sare
    peste fișiere deja importate, ca să nu suprascrie modificările
    făcute manual de utilizator în UI (status, cantitate confirmată etc.)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        file_src = os.path.basename(filepath)

        # Verifică dacă a fost deja importat (skip-if-exists default)
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

        order_no  = parse_order_no(filepath)
        pfi_date  = parse_pfi_date(filepath)
        order_date = pfi_date or parse_order_date(filepath)
        status    = detect_status(file_src)
        total_usd = round(sum(line.get("total_valuta") or 0 for line in lines), 2)
        file_mtime = date.fromtimestamp(os.path.getmtime(filepath))
        lead = lead_time_days(conn, "Basilur")
        eta = estimate_eta(order_date, file_mtime, lead)

        if existing and force:
            print(f"    --force: șterg comanda existentă id={existing[0]}")
            conn.execute("DELETE FROM comenzi_furnizori_linii WHERE comanda_id = ?", (existing[0],))
            conn.execute("DELETE FROM comenzi_furnizori WHERE id = ?", (existing[0],))

        obs_status = "PFI primit, în tranzit" if status == "in_tranzit" \
                     else "Comandă trimisă, NEconfirmată de furnizor"
        cur = conn.execute("""
            INSERT INTO comenzi_furnizori
                (nr_comanda, furnizor, data_comanda, data_estimata_livrare, eta,
                 status, file_source, total_usd, moneda, observatii)
            VALUES (?, 'Basilur', COALESCE(?, date('now')), ?, ?,
                    ?, ?, ?, 'USD', ?)
        """, (order_no, order_date, eta, eta, status, file_src, total_usd,
              f"Importat din {file_src} | {obs_status} | ETA estimat +{lead}z lead time"))
        comanda_id = cur.lastrowid

        # Insert lines, mapping code → sku
        inserted = 0
        unmatched = 0
        for line in lines:
            sku = map_basilur_code_to_sku(conn, line["cod_furnizor"])
            obs_linie = None
            if not sku:
                sku = line["descriere"] or line["cod_furnizor"]
                unmatched += 1
                # Marker pentru POSM/textile/canister fără SKU în stoc
                # (ex: P0009 tricouri, 72510 canister, 72789 cold brew samples)
                obs_linie = "POSM/textile (fara SKU in stoc)"
            conn.execute("""
                INSERT INTO comenzi_furnizori_linii
                    (comanda_id, sku, cod_furnizor, descriere,
                     units_per_carton, cantitate_baxuri, cantitate_comandata,
                     pret_valuta, moneda, total_valuta,
                     gross_kg, net_kg, cbm, observatii)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'USD', ?, ?, ?, ?, ?)
            """, (
                comanda_id, sku, line["cod_furnizor"], line["descriere"],
                line["units_per_carton"], line["cantitate_baxuri"],
                line["cantitate_comandata"], line["pret_valuta"],
                line["total_valuta"], line["gross_kg"],
                line["net_kg"], line["cbm"], obs_linie,
            ))
            inserted += 1
        conn.commit()
        print(f"    OK comanda_id={comanda_id} | {inserted} linii ({unmatched} fara mapare SKU) | total {total_usd:,.2f} USD")
        return inserted
    finally:
        conn.close()


def run(filepath=None, force=False):
    if filepath:
        return import_file(filepath, force=force)

    if not os.path.isdir(DEFAULT_DIR):
        print(f"EROARE: nu gasesc directorul {DEFAULT_DIR}")
        return 0

    total = 0
    for fname in sorted(os.listdir(DEFAULT_DIR)):
        if fname.lower().endswith((".xls", ".xlsx")) and not fname.startswith("~$"):
            total += import_file(os.path.join(DEFAULT_DIR, fname), force=force)
    return total


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    fp = args[0] if args else None
    run(fp, force=force)
