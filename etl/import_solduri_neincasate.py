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
    telefon     TEXT
)
"""

COLS = ["nrdl", "datadl", "term_pl_cl", "plafon", "numecli", "codcli",
        "cfcli", "vtdl", "sumdeincas", "factout", "numeag", "canal", "telefon"]

# ERP header name (lowercase) -> our key
COL_MAP = {
    "nrdl": "nrdl", "datadl": "datadl", "term_pl_cl": "term_pl_cl",
    "plafon": "plafon", "numecli": "numecli", "codcli": "codcli",
    "cfcli": "cfcli", "vtdl": "vtdl", "sumdeincas": "sumdeincas",
    "factout": "factout", "numeag": "numeag", "nume": "canal",
    "telefon": "telefon",
}


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


def parse_solduri_xls(filepath):
    book = xlrd.open_workbook(filepath)
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

    def datestr(row):
        c = idx.get("datadl")
        if c is None:
            return None
        v = ws.cell_value(row, c)
        if isinstance(v, float) and v > 0:
            try:
                return xlrd.xldate_as_datetime(v, book.datemode).strftime("%Y-%m-%d")
            except Exception:
                return None
        s = _s(v)
        return s[:10] if s else None

    out = []
    for row in range(1, ws.nrows):
        numecli = _s(cell(row, "numecli"))
        factout = _s(cell(row, "factout"))
        if not numecli and not factout:
            continue
        out.append({
            "nrdl": _s(cell(row, "nrdl")),
            "datadl": datestr(row),
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
        })
    return out


def run(filepath):
    rows = parse_solduri_xls(filepath)
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
