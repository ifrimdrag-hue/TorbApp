"""
Import stoc din exportul ERP (.xls format).

Format fișier: docs_input/DD.MM.YYYY/stoc DD.MM.YYYY.xls
Creează tabelul `stoc` în torb.db dacă nu există.
Fiecare import stochează un snapshot cu data exportului.

Usage:
    python import_stoc.py [<cale_fisier.xls>]
    # fără argumente: detectează automat cel mai recent folder datat
"""

import sys
import os
import re
import sqlite3
import xlrd
from datetime import date

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "data/torb.db"
DOCS_PATH = "docs_input"

CREATE_STOC = """
CREATE TABLE IF NOT EXISTS stoc (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    data_snapshot   TEXT NOT NULL,
    cod_produs      TEXT,
    cod_mare        TEXT,
    sku             TEXT,
    furnizor        TEXT,
    gama            TEXT,
    cantitate       REAL,
    pret_achizitie  REAL,
    data_intrare    TEXT,
    nr_zile_stoc    INTEGER,
    greutate        REAL,
    um              TEXT DEFAULT 'BUC',
    cod_sortiment   TEXT,
    codbare         TEXT,
    UNIQUE(data_snapshot, cod_produs, data_intrare)
)
"""

CREATE_STOC_IDX = [
    "CREATE INDEX IF NOT EXISTS idx_stoc_snapshot ON stoc(data_snapshot)",
    "CREATE INDEX IF NOT EXISTS idx_stoc_sku      ON stoc(sku)",
    "CREATE INDEX IF NOT EXISTS idx_stoc_furnizor ON stoc(furnizor)",
]


def derive_furnizor(sku: str, cp_lookup: dict = None, cod_produs: str = None) -> str:
    """Determină furnizorul. Întâi din lookup cod_produs (din tranzacțiile
    istorice — captează produsele fără prefix clar, ex: MISS MAGIC = Solvex),
    apoi fallback prin prefix de SKU."""
    if cp_lookup is not None and cod_produs and str(cod_produs) in cp_lookup:
        return cp_lookup[str(cod_produs)]
    if not sku:
        return "Altele"
    s = str(sku).strip()
    if s.startswith("B.") or s.startswith('B."') or s.startswith("WB."):
        return "Basilur"
    if s.startswith("KL "):
        return "KingsLeaf"
    if s.upper().startswith("CELMAR") or s.startswith("C."):
        return "Celmar"
    # Celmar Polonia: ceaiuri/tincturi cu EAN 5902795 / 5902480
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
    # Solvex: vopsea de păr Miss Magic + șampoane / display-uri proprii
    for solvex_marker in ("MISS MAGIC", "SAMPON BLUE MAGIC", "STAND VOPSEA"):
        if solvex_marker in su:
            return "Solvex"
    if su.startswith("IMAJ "):
        return "Solvex"
    # Basilur HORECA: dispensere si pahare HORECA, accesorii cu cod 70xxx-72xxx
    if su.startswith("HORECA ") or su.startswith("H "):
        return "Basilur"
    if (su.startswith("CUTIE HORECA") or su.startswith("CUTIE LEMN")
            or su.startswith("CUTIE INCHISA") or su.startswith("PUNGA ")
            or su.startswith("PUNGI ") or su.startswith("PAHAR ")):
        return "Basilur"
    # Cosmetice: linie Selvert Thermal (creme/măști/seruri)
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


def build_cod_furnizor_lookup(conn):
    """cod_produs → furnizor din tranzacțiile istorice (mapare automată)."""
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT cod_produs, furnizor FROM tranzactii WHERE furnizor IS NOT NULL AND furnizor != 'Altele'")
    return {str(row[0]): row[1] for row in cur.fetchall() if row[0] is not None}


def derive_gama(furnizor: str, sku: str) -> str:
    """Map furnizor → gama. KingsLeaf kept as KingsLeaf until Kings/Leaf split is defined."""
    gama_map = {
        "Basilur":   "Basilur",
        "Celmar":    "Celmar",
        "KingsLeaf": "KingsLeaf",
        "Toras":     "Toras",
        "Leonex":    "Leonex",
        "Tipson":    "Tipson",
        "Delaviuda": "Delaviuda",
        "Solvex":    "Solvex",
        "Cosmetice": "Cosmetice",
    }
    return gama_map.get(furnizor, furnizor or "Altele")


def xlrd_date(val, book):
    """Convert xlrd date serial to ISO string."""
    try:
        if isinstance(val, float) and val > 0:
            t = xlrd.xldate_as_datetime(val, book.datemode)
            return t.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def find_latest_stoc_file():
    date_pattern = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
    candidates = []
    for entry in os.listdir(DOCS_PATH):
        if date_pattern.match(entry):
            folder = os.path.join(DOCS_PATH, entry)
            if os.path.isdir(folder):
                for f in os.listdir(folder):
                    if f.lower().startswith("stoc") and (
                        f.lower().endswith(".xls") or f.lower().endswith(".xlsx")
                    ):
                        day, month, year = entry.split(".")
                        folder_date = date(int(year), int(month), int(day))
                        candidates.append((folder_date, os.path.join(folder, f)))
    # Fallback: caută și în docs_input/rapoarte/
    rapoarte = os.path.join(DOCS_PATH, "rapoarte")
    if os.path.isdir(rapoarte):
        for f in os.listdir(rapoarte):
            fl = f.lower()
            if fl.startswith("stoc") and (fl.endswith(".xls") or fl.endswith(".xlsx")):
                # Încearcă să extragă data din numele fișierului (ex: "stoc 20.05.2026.xls")
                m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", f)
                if m:
                    day, month, year = m.groups()
                    file_date = date(int(year), int(month), int(day))
                else:
                    file_date = date.today()
                candidates.append((file_date, os.path.join(rapoarte, f)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0]


def snapshot_date_from_path(filepath):
    """Extract date from parent folder name (DD.MM.YYYY) or filename."""
    parent = os.path.basename(os.path.dirname(filepath))
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", parent)
    if m:
        day, month, year = m.groups()
        return f"{year}-{month}-{day}"
    # fallback: today
    return date.today().isoformat()


def read_stoc_xls(filepath, cp_lookup=None):
    print(f"  Citesc: {filepath}")
    book = xlrd.open_workbook(filepath)
    ws = book.sheet_by_index(0)

    if ws.nrows < 2:
        print("    → Fișier gol.")
        return []

    header = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
    # Expected: cod, cantit, codg, data, nrzilestoc, pret, denprod, um,
    #           ambalaj, codmare, codn, greutate, nume, locdep, codsort, codbare

    col = {name: i for i, name in enumerate(header)}

    def get(row_idx, name, default=None):
        i = col.get(name)
        if i is None:
            return default
        v = ws.cell_value(row_idx, i)
        return v if v != "" else default

    rows_raw = []
    for row_idx in range(1, ws.nrows):
        cod = get(row_idx, "cod")
        if cod is None:
            continue

        denprod = str(get(row_idx, "denprod", "") or "").strip()
        furnizor = derive_furnizor(denprod, cp_lookup, cod)
        gama = derive_gama(furnizor, denprod)

        data_intrare = xlrd_date(get(row_idx, "data"), book)
        nrzile = get(row_idx, "nrzilestoc")
        try:
            nrzile = int(nrzile) if nrzile is not None else None
        except (ValueError, TypeError):
            nrzile = None

        rows_raw.append({
            "cod_produs":     str(cod).strip(),
            "cod_mare":       str(get(row_idx, "codmare", "") or "").strip() or None,
            "sku":            denprod or None,
            "furnizor":       furnizor,
            "gama":           gama,
            "cantitate":      float(get(row_idx, "cantit", 0) or 0),
            "pret_achizitie": float(get(row_idx, "pret", 0) or 0),
            "data_intrare":   data_intrare,
            "nr_zile_stoc":   nrzile,
            "greutate":       float(get(row_idx, "greutate", 0) or 0) or None,
            "um":             str(get(row_idx, "um", "BUC") or "BUC").strip(),
            "cod_sortiment":  str(get(row_idx, "codsort", "") or "").strip() or None,
            "codbare":        str(get(row_idx, "codbare", "") or "").strip() or None,
        })

    # Agregare: ERP-ul poate emite mai multe rânduri cu același (cod_produs, data_intrare)
    # pentru depozite/loturi diferite. UNIQUE(snapshot, cod_produs, data_intrare) ar păstra
    # doar ultimul rând via INSERT OR REPLACE — cantitățile trebuie sumate explicit.
    agg = {}
    for r in rows_raw:
        key = (r["cod_produs"], r["data_intrare"])
        if key not in agg:
            agg[key] = dict(r)
        else:
            existing = agg[key]
            old_qty = existing["cantitate"]
            add_qty = r["cantitate"]
            total_qty = old_qty + add_qty
            if total_qty > 0:
                existing["pret_achizitie"] = (
                    existing["pret_achizitie"] * old_qty + r["pret_achizitie"] * add_qty
                ) / total_qty
            existing["cantitate"] = total_qty

    rows_out = list(agg.values())
    if len(rows_raw) != len(rows_out):
        print(f"    → Agregate {len(rows_raw):,} rânduri → {len(rows_out):,} poziții unice (diferența: duplicate pe aceeași dată)")
    print(f"    → {len(rows_out):,} poziții stoc citite")
    return rows_out


def _populate_stoc_expirare(conn, data_snapshot: str):
    """Sincronizează stoc_expirare din ultimul snapshot de stoc."""
    conn.execute("DELETE FROM stoc_expirare WHERE data_snapshot = ?", (data_snapshot,))
    conn.execute("""
        INSERT INTO stoc_expirare
            (cod_produs, sku, furnizor, gama, data_intrare, cantitate, pret_achizitie, data_snapshot)
        SELECT cod_produs, sku, furnizor, gama, data_intrare, SUM(cantitate),
               AVG(pret_achizitie), data_snapshot
        FROM stoc
        WHERE data_snapshot = ?
          AND cantitate > 0
        GROUP BY cod_produs, sku, furnizor, gama, data_intrare, data_snapshot
    """, (data_snapshot,))


def insert_stoc(conn, rows, snapshot):
    cols = [
        "data_snapshot", "cod_produs", "cod_mare", "sku", "furnizor", "gama",
        "cantitate", "pret_achizitie", "data_intrare", "nr_zile_stoc",
        "greutate", "um", "cod_sortiment", "codbare",
    ]
    placeholders = ", ".join(["?" for _ in cols])
    col_names = ", ".join(cols)
    sql = f"INSERT OR REPLACE INTO stoc ({col_names}) VALUES ({placeholders})"

    data = []
    for r in rows:
        data.append([snapshot] + [r[c] for c in cols[1:]])

    cursor = conn.cursor()
    cursor.executemany(sql, data)
    inserted = cursor.rowcount
    _populate_stoc_expirare(conn, snapshot)
    conn.commit()
    return inserted


def run(filepath=None):
    if filepath is None:
        result = find_latest_stoc_file()
        if result is None:
            print("EROARE: Nu am găsit niciun fișier stoc*.xls în foldere datate.")
            return 0
        _, filepath = result

    snapshot = snapshot_date_from_path(filepath)
    print(f"  Snapshot: {snapshot}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute(CREATE_STOC)
    for idx in CREATE_STOC_IDX:
        conn.execute(idx)
    conn.commit()

    cp_lookup = build_cod_furnizor_lookup(conn)
    rows = read_stoc_xls(filepath, cp_lookup=cp_lookup)
    inserted = insert_stoc(conn, rows, snapshot)
    print(f"    → Stoc importat: {inserted:,} rânduri (snapshot {snapshot})")

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT data_snapshot) FROM stoc")
    n_snapshots = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(cantitate) FROM stoc WHERE data_snapshot=?", (snapshot,))
    total_units = cursor.fetchone()[0]
    print(f"    → Snapshots în DB: {n_snapshots} | Total unități stoc curent: {total_units:,.0f}")

    conn.close()
    return inserted


if __name__ == "__main__":
    filepath = sys.argv[1] if len(sys.argv) > 1 else None
    run(filepath)
