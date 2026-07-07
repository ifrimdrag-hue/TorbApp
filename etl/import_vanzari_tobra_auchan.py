"""
Import vânzări Tobra → Auchan, atașate ca tranzacții Torb cu agent Oana Filip.

Excepție de business: vânzările Torb către Auchan sunt facturate prin Tobra.
Acest script preia tot istoricul facturat de Tobra către Auchan și îl injectează
în `tranzactii` ca și cum ar fi vânzări Torb→Auchan, cu agentul Oana Filip
(care e deja alocat pentru Auchan în Torb).

Fisier sursa:    docs_input/rapoarte/auchan tobra 2024-2026.xls
Suprascrieri:    vezi app/business_constants.py (AUCHAN_*, TOBRA_*)
Pastrate:        nr_factura (prefix 'TOBRA' = marker), nr_dl, cod_produs, etc.
Dedup:           UNIQUE(nr_dl, cod_produs, nr_factura)

Usage:
    python import_vanzari_tobra_auchan.py [<cale_fisier.xls>]
"""

import sys
import os
import sqlite3
import xlrd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from business_constants import (  # noqa: E402
    AUCHAN_AGENT,
    AUCHAN_CLIENT_NAME,
    AUCHAN_COD_CLIENT,
    AUCHAN_TIP_CLIENT,
    TOBRA_COD_CLIENT,
    TOBRA_COST_WINDOW_DAYS,
    TOBRA_INVOICE_PREFIX,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "data/torb.db"
DEFAULT_FILE = "docs_input/rapoarte/auchan tobra 2024-2026.xls"


DB_COLS = [
    "luna", "an", "data_dl", "nr_dl", "nr_factura", "nr_comanda",
    "cod_produs", "sku", "furnizor", "um",
    "cantitate", "pret_vanzare", "tva_pct", "pret_cumparare",
    "val_bruta", "val_neta", "val_achizitie", "val_usd", "marja_bruta",
    "discount_pct", "discount_val",
    "client", "cod_client", "cui_client", "tip_client",
    "oras_client", "judet_client", "adresa_client",
    "agent", "adr_livrare", "locatie",
]


def derive_furnizor(sku: str, cp_lookup: dict, cod_produs: str) -> str:
    furn = _furnizor_from_sku_name(sku)
    if furn != "Altele":
        return furn
    # Fallback only: Tobra's cod_produs numbering collides with Torb's ERP codes
    # (e.g. 1508 = 'KL ENGLISH BREAKFAST' at Tobra but 'C.GOPLANA' / Celmar at
    # Torb), so the SKU-name rules must win whenever they match.
    if cod_produs and cod_produs in cp_lookup:
        return cp_lookup[cod_produs]
    return "Altele"


def _furnizor_from_sku_name(sku: str) -> str:
    if not sku:
        return "Altele"
    s = str(sku).strip()
    if s.upper().startswith("B.ECO ORGANSIA"):
        return "Organsia"
    if s.startswith("B.") or s.startswith('B."') or s.startswith("WB."):
        return "Basilur"
    if s.startswith("KL "):
        return "KingsLeaf"
    if s.upper().startswith("CELMAR") or s.startswith("C."):
        return "Celmar"
    if "5902795" in s or "5902480" in s:
        return "Celmar"
    if s.startswith("T."):
        return "Toras"
    if s.startswith("TS "):
        return "Tipson"
    if s.startswith("DEL.") or s.startswith("ALM."):
        return "Delaviuda"
    su = s.upper()
    for leonex_prefix in ("LEONEX", "BETISOARE", "DISCURI", "VATA ", "BILUTE", "SERVETELE",
                          "W.BETISOARE", "W.DISCURI", "W.SERVETELE"):
        if su.startswith(leonex_prefix):
            return "Leonex"
    for solvex_marker in ("MISS MAGIC", "SAMPON BLUE MAGIC", "STAND VOPSEA"):
        if solvex_marker in su:
            return "Solvex"
    if su.startswith("IMAJ "):
        return "Solvex"
    # HORECA formats of the virtual sub-brands keep their own brand
    # (TS = Tipson 80xxx, KL = KingsLeaf 90xxx, Organsia) — must be checked
    # before the generic HORECA -> Basilur rule.
    if su.startswith("HORECA TS ") or su.startswith("H TS "):
        return "Tipson"
    if su.startswith("HORECA KL ") or su.startswith("H KL "):
        return "KingsLeaf"
    if su.startswith("HORECA ORGANSIA") or su.startswith("HORECA B.ECO ORGANSIA"):
        return "Organsia"
    if su.startswith("HORECA ") or su.startswith("H "):
        return "Basilur"
    if (su.startswith("CUTIE HORECA") or su.startswith("CUTIE LEMN")
            or su.startswith("CUTIE INCHISA") or su.startswith("PUNGA ")
            or su.startswith("PUNGI ") or su.startswith("PAHAR ")):
        return "Basilur"
    cosm_markers = ("PRIME RENEWING", "INTENSE REGEN", "REGENERATING MASK",
                    "V-LIFT", "V-FIRM", "ELIXIR ", "VITAL ", "DETO2X",
                    "LUMI BOOST", "LUMIMASK", "H2O BOOST", "FLUID FALLS",
                    "BUBBLE FALLS", "ICY FALLS", "HYDRA3",
                    "MOISTURIZING ", "HUILE ", "LADY CODE", "BIO REV ",
                    "PURIFYING PACK", "SEA BLISS", "CREME DE MASQUE",
                    "HAND 24 HOUR", "PRIMARY VEIL", "BATHROBE ",
                    "HAIR BRUSH", "HEADBAND ")
    for m in cosm_markers:
        if su.startswith(m):
            return "Cosmetice"
    return "Altele"


def xlrd_date_str(val, datemode):
    if val in (None, ""):
        return None
    try:
        if isinstance(val, (int, float)) and val > 0:
            t = xlrd.xldate_as_datetime(val, datemode)
            return t.strftime("%Y-%m-%d"), t.date()
    except Exception:
        pass
    return None


def normalize_str(val):
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def normalize_num(val):
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def lookup_tobra_cost(conn, cod_produs, data_dl_str):
    """True Torb acquisition cost for cod_produs at date data_dl_str.

    Returns (cost, source): "window" = simple avg over the last
    TOBRA_COST_WINDOW_DAYS days (exclusive start, inclusive end);
    "last_known" = avg of entries on the most recent data_dl <= date.
    (None, None) when corr_vanzari_tobra has no usable entry.
    """
    d = datetime.strptime(data_dl_str, "%Y-%m-%d").date()
    window_start = (d - timedelta(days=TOBRA_COST_WINDOW_DAYS)).strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute(
        "SELECT AVG(pret_cumparare) FROM corr_vanzari_tobra"
        " WHERE cod_produs = ? AND pret_cumparare IS NOT NULL"
        " AND data_dl > ? AND data_dl <= ?",
        (cod_produs, window_start, data_dl_str),
    )
    avg = cur.fetchone()[0]
    if avg is not None:
        return round(avg, 4), "window"
    cur.execute(
        "SELECT AVG(pret_cumparare) FROM corr_vanzari_tobra"
        " WHERE cod_produs = ? AND pret_cumparare IS NOT NULL"
        " AND data_dl = (SELECT MAX(data_dl) FROM corr_vanzari_tobra"
        "  WHERE cod_produs = ? AND pret_cumparare IS NOT NULL"
        "  AND data_dl <= ?)",
        (cod_produs, cod_produs, data_dl_str),
    )
    last = cur.fetchone()[0]
    if last is not None:
        return round(last, 4), "last_known"
    return None, None


def apply_cost_override(conn, records):
    """Override pret_cumparare with the true Torb cost from corr_vanzari_tobra
    and recompute val_achizitie + marja_bruta. Rows without a known cost
    keep the value from the Tobra file. Mutates records; returns counts."""
    cache = {}
    counts = {"window": 0, "last_known": 0, "excel": 0}
    for r in records:
        cod = r["cod_produs"]
        if not cod:
            counts["excel"] += 1
            continue
        key = (cod, r["data_dl"])
        if key not in cache:
            cache[key] = lookup_tobra_cost(conn, cod, r["data_dl"])
        cost, source = cache[key]
        if cost is None:
            counts["excel"] += 1
            continue
        counts[source] += 1
        r["pret_cumparare"] = cost
        r["val_achizitie"] = round((r["cantitate"] or 0) * cost, 4)
        r["marja_bruta"] = round((r["val_neta"] or 0) - r["val_achizitie"], 4)
    print(f"    -> Cost real Torb: {counts['window']:,} medie {TOBRA_COST_WINDOW_DAYS}z"
          f" | {counts['last_known']:,} ultimul cost | {counts['excel']:,} valoare fisier")
    return counts


def build_cod_furnizor_lookup(conn):
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT cod_produs, furnizor FROM tranzactii WHERE furnizor IS NOT NULL")
    return {str(row[0]): row[1] for row in cur.fetchall()}


def build_cod_sku_lookup(conn):
    """Returns {cod_produs: sku} from ERP records (non-Auchan) for SKU name normalization.
    Tobra XLS may omit parentheses around EAN codes that ERP includes."""
    cur = conn.cursor()
    cur.execute(
        "SELECT cod_produs, MAX(sku) AS sku FROM tranzactii "
        "WHERE cod_produs IS NOT NULL AND cod_produs != '' "
        f"  AND cod_client != '{AUCHAN_COD_CLIENT}' "
        "GROUP BY cod_produs"
    )
    return {str(row[0]): row[1] for row in cur.fetchall() if row[1]}


def read_tobra_xls(filepath):
    print(f"  Citesc: {filepath}")
    book = xlrd.open_workbook(filepath)
    ws = book.sheet_by_index(0)
    if ws.nrows < 2:
        print("    → Fișier gol.")
        return [], book.datemode

    header = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
    col = {name: i for i, name in enumerate(header)}

    def get(row_idx, name, default=None):
        i = col.get(name)
        if i is None:
            return default
        v = ws.cell_value(row_idx, i)
        return v if v != "" else default

    rows = []
    for ri in range(1, ws.nrows):
        rows.append({h: get(ri, h) for h in header})
    print(f"    → {len(rows):,} rânduri brute citite")
    return rows, book.datemode


def process_rows(rows_raw, cp_lookup, datemode, cod_sku_lookup=None):
    records = []
    skipped_no_date = 0
    for raw in rows_raw:
        data_dl_raw = raw.get("datadl")
        if data_dl_raw in (None, ""):
            skipped_no_date += 1
            continue
        try:
            dt = xlrd.xldate_as_datetime(float(data_dl_raw), datemode).date()
        except Exception:
            skipped_no_date += 1
            continue

        sku        = normalize_str(raw.get("den_b"))
        cod_produs = normalize_str(raw.get("codprod"))
        # Normalize SKU to match ERP canonical form (Tobra XLS may omit parentheses around EAN)
        if cod_produs and cod_sku_lookup and cod_produs in cod_sku_lookup:
            sku = cod_sku_lookup[cod_produs]
        cantitate = normalize_num(raw.get("cantit")) or 0
        pvanz     = normalize_num(raw.get("pvanz")) or 0
        pcump     = normalize_num(raw.get("pcump")) or 0
        discount  = normalize_num(raw.get("discount")) or 0

        val_bruta     = round(cantitate * pvanz, 4)
        val_neta      = round(val_bruta - discount, 4)
        val_achizitie = round(cantitate * pcump, 4)
        marja_bruta   = round(val_neta - val_achizitie, 4)

        record = {
            "luna":           dt.month,
            "an":             dt.year,
            "data_dl":        dt.strftime("%Y-%m-%d"),
            "nr_dl":          normalize_str(raw.get("nrdl")),
            "nr_factura":     normalize_str(raw.get("factout")),
            "nr_comanda":     normalize_str(raw.get("nrcomandametro")),
            "cod_produs":     cod_produs,
            "sku":            sku,
            "furnizor":       derive_furnizor(sku or "", cp_lookup, cod_produs or ""),
            "um":             normalize_str(raw.get("um")) or "BUC",
            "cantitate":      cantitate,
            "pret_vanzare":   pvanz,
            "tva_pct":        normalize_num(raw.get("tva")),
            "pret_cumparare": pcump,
            "val_bruta":      val_bruta,
            "val_neta":       val_neta,
            "val_achizitie":  val_achizitie,
            "val_usd":        None,
            "marja_bruta":    marja_bruta,
            "discount_pct":   normalize_num(raw.get("procent")) or normalize_num(raw.get("discproc")),
            "discount_val":   discount,
            # Hard-coded overrides — Tobra→Auchan attached as Torb→Auchan via Oana
            "client":         AUCHAN_CLIENT_NAME,
            "cod_client":     AUCHAN_COD_CLIENT,
            "cui_client":     normalize_str(raw.get("cfcli")),
            "tip_client":     AUCHAN_TIP_CLIENT,
            "oras_client":    normalize_str(raw.get("localcli")),
            "judet_client":   normalize_str(raw.get("judet")),
            "adresa_client":  normalize_str(raw.get("adresa")),
            "agent":          AUCHAN_AGENT,
            "adr_livrare":    normalize_str(raw.get("adr_livr")),
            "locatie":        normalize_str(raw.get("locatie")),
        }
        records.append(record)

    if skipped_no_date:
        print(f"    → {skipped_no_date} rânduri sărite (data lipsă)")
    return records


def insert_rows(conn, records):
    placeholders = ", ".join(["?" for _ in DB_COLS])
    cols = ", ".join(DB_COLS)
    sql = f"INSERT OR IGNORE INTO tranzactii ({cols}) VALUES ({placeholders})"
    data = [[r[c] for c in DB_COLS] for r in records]
    cur = conn.cursor()
    cur.executemany(sql, data)
    inserted = cur.rowcount
    conn.commit()
    return inserted


def delete_torb_to_tobra_entries(conn):
    """Șterge facturile Torb→Tobra (cod_client=719) — sunt redundante cu
    Tobra→Auchan importate aici și ar duce la dublu-numărare."""
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(val_neta), 0) FROM tranzactii WHERE cod_client = ?",
        (TOBRA_COD_CLIENT,),
    )
    n, val = cur.fetchone()
    if n == 0:
        print("    → Nicio factură Torb→Tobra de șters.")
        return 0
    cur.execute("DELETE FROM tranzactii WHERE cod_client = ?", (TOBRA_COD_CLIENT,))
    conn.commit()
    print(f"    → Șterse {n:,} facturi Torb→Tobra (cod_client={TOBRA_COD_CLIENT}) "
          f"= {val:,.0f} RON (anti-dublu-numărare)")
    return n


def run(filepath=None):
    filepath = filepath or DEFAULT_FILE
    if not os.path.exists(filepath):
        print(f"EROARE: nu găsesc fișierul {filepath}")
        return 0

    conn = sqlite3.connect(DB_PATH)
    cp_lookup = build_cod_furnizor_lookup(conn)
    cod_sku_lookup = build_cod_sku_lookup(conn)

    rows_raw, datemode = read_tobra_xls(filepath)
    records = process_rows(rows_raw, cp_lookup, datemode, cod_sku_lookup)
    print(f"    → {len(records):,} rânduri procesate")

    apply_cost_override(conn, records)

    inserted = insert_rows(conn, records)
    skipped = len(records) - inserted
    print(f"    → Inserate: {inserted:,} | Duplicate ignorate: {skipped:,}")

    # După import: șterge intrările Torb→Tobra (cod_client=719) ca să eviți
    # dublu-numărarea cu noile înregistrări Tobra→Auchan.
    delete_torb_to_tobra_entries(conn)

    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*), SUM(val_neta), MIN(data_dl), MAX(data_dl)"
        " FROM tranzactii WHERE nr_factura LIKE ?",
        (TOBRA_INVOICE_PREFIX + "%",),
    )
    n, vn, d_min, d_max = cur.fetchone()
    print(f"    → Total Tobra→Auchan în DB: {n:,} tranz | {(vn or 0):,.0f} RON | {d_min} → {d_max}")

    cur.execute(
        "SELECT COUNT(*), SUM(val_neta) FROM tranzactii"
        " WHERE cod_client=? AND agent=? AND nr_factura LIKE ?",
        (AUCHAN_COD_CLIENT, AUCHAN_AGENT, TOBRA_INVOICE_PREFIX + "%"),
    )
    n_oa, v_oa = cur.fetchone()
    print(f"    → Atribuite la {AUCHAN_AGENT} pentru Auchan: {n_oa:,} tranz | {(v_oa or 0):,.0f} RON")

    conn.close()
    return inserted


if __name__ == "__main__":
    fp = sys.argv[1] if len(sys.argv) > 1 else None
    run(fp)
