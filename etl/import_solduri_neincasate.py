"""Import solduri neincasate din exportul ERP (.xls).

Un rand = un document deschis (factura/avans). Replace-only: sterge tot si
reinsereaza. data_raport = data incarcarii (azi). Scadenta se calculeaza la
citire (datadl + term_pl_cl), nu se ia din fisier.

Usage:
    python etl/import_solduri_neincasate.py <cale_fisier.xls>
"""

import sys
import sqlite3
import xlrd
from datetime import date

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "data/torb.db"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS solduri_neincasate (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    data_raport TEXT NOT NULL,
    nrdl        TEXT,
    datadl      TEXT,
    term_pl_cl  INTEGER,
    plafon      REAL,
    numecli     TEXT,
    codcli      TEXT,
    cfcli       TEXT,
    vtdl        REAL,
    sumdeincas  REAL,
    factout     TEXT,
    numeag      TEXT,
    canal       TEXT,
    telefon     TEXT,
    discount    REAL,
    cec         INTEGER,
    scad_cec    TEXT,
    cec_doc     TEXT
)
"""

COLS = ["nrdl", "datadl", "term_pl_cl", "plafon", "numecli", "codcli",
        "cfcli", "vtdl", "sumdeincas", "factout", "numeag", "canal", "telefon",
        "discount", "cec", "scad_cec", "cec_doc"]

# ERP header name (lowercase) -> our key
COL_MAP = {
    "nrdl": "nrdl", "datadl": "datadl", "term_pl_cl": "term_pl_cl",
    "plafon": "plafon", "numecli": "numecli", "codcli": "codcli",
    "cfcli": "cfcli", "vtdl": "vtdl", "sumdeincas": "sumdeincas",
    "factout": "factout", "numeag": "numeag", "nume": "canal",
    "telefon": "telefon", "discount": "discount", "cec": "cec",
    "scad_cec": "scad_cec", "_dl": "cec_doc",
}

# Date columns: read as Excel serial → ISO, junk placeholders ("  -   -") → None
DATE_KEYS = ("datadl", "scad_cec")


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _f(v):
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _i(v):
    f = _f(v)
    return int(round(f)) if f is not None else None


def _open(filepath):
    """Open an ERP .xls. The newer export mislabels its codepage (declares
    cp1252 but stores Romanian Latin-2 bytes), so fall back to iso-8859-2 when
    the default decode raises."""
    try:
        return xlrd.open_workbook(filepath)
    except UnicodeDecodeError:
        return xlrd.open_workbook(filepath, encoding_override="iso-8859-2")


def _xldate(v, datemode):
    """Excel serial → 'YYYY-MM-DD'. ERP junk placeholders ('  -   -') → None."""
    if isinstance(v, float) and v > 0:
        try:
            return xlrd.xldate_as_datetime(v, datemode).strftime("%Y-%m-%d")
        except Exception:
            return None
    s = _s(v)
    return s[:10] if s and s[0].isdigit() else None


def parse_solduri_xls(filepath):
    book = _open(filepath)
    ws = book.sheet_by_index(0)
    if ws.nrows < 2:
        return []
    header = [str(ws.cell_value(0, c)).strip().lower() for c in range(ws.ncols)]
    idx = {}
    for c, name in enumerate(header):
        if name in COL_MAP and COL_MAP[name] not in idx:
            idx[COL_MAP[name]] = c

    def cell(row, key):
        c = idx.get(key)
        return ws.cell_value(row, c) if c is not None else None

    def datecell(row, key):
        return _xldate(cell(row, key), book.datemode)

    out = []
    for row in range(1, ws.nrows):
        numecli = _s(cell(row, "numecli"))
        factout = _s(cell(row, "factout"))
        if not numecli and not factout:
            continue
        out.append({
            "nrdl": _s(cell(row, "nrdl")),
            "datadl": datecell(row, "datadl"),
            "term_pl_cl": _i(cell(row, "term_pl_cl")),
            "plafon": _f(cell(row, "plafon")),
            "numecli": numecli,
            "codcli": _s(cell(row, "codcli")),
            "cfcli": _s(cell(row, "cfcli")),
            "vtdl": _f(cell(row, "vtdl")),
            "sumdeincas": _f(cell(row, "sumdeincas")),
            "factout": factout,
            "numeag": _s(cell(row, "numeag")),
            "canal": _s(cell(row, "canal")),
            "telefon": _s(cell(row, "telefon")),
            "discount": _f(cell(row, "discount")),
            "cec": _i(cell(row, "cec")),
            "scad_cec": datecell(row, "scad_cec"),
            "cec_doc": _s(cell(row, "cec_doc")),
        })
    return out


def _merge_cec(rows):
    """Fold cheque rows (cec=1) into the invoice they cover.

    A cheque row's `cec_doc` (ERP `_dl`) holds the `nrdl` of the invoice the
    cheque covers, and duplicates that invoice's balance. For each cheque row
    matching an invoice, copy the four cheque columns (discount, cec, scad_cec,
    cec_doc) onto every matching invoice row and drop the cheque row (stops the
    balance double-counting). Cheque rows matching no invoice are kept as-is.
    """
    index = {}
    for r in rows:
        if not r.get("cec"):
            index.setdefault(r["nrdl"], []).append(r)
    drop = set()
    for i, r in enumerate(rows):
        if not r.get("cec"):
            continue
        targets = index.get(r.get("cec_doc"))
        if not targets:
            continue
        for t in targets:
            t["cec"] = 1
            t["scad_cec"] = r["scad_cec"]
            t["cec_doc"] = r["cec_doc"]
            t["discount"] = r["discount"]
        drop.add(i)
    return [r for i, r in enumerate(rows) if i not in drop]


def run(filepath):
    rows = _merge_cec(parse_solduri_xls(filepath))
    data_raport = date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(CREATE_SQL)
    conn.execute("DELETE FROM solduri_neincasate")
    placeholders = ", ".join(["?"] * (len(COLS) + 1))
    sql = (f"INSERT INTO solduri_neincasate (data_raport, {', '.join(COLS)}) "
           f"VALUES ({placeholders})")
    conn.executemany(sql, [[data_raport] + [r[c] for c in COLS] for r in rows])
    conn.commit()
    conn.close()
    print(f"  → Solduri importate: {len(rows):,} randuri (raport {data_raport})")
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("EROARE: lipseste calea fisierului .xls")
        sys.exit(1)
    run(sys.argv[1])
