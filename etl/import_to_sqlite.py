"""
Torb Logistic — Excel → SQLite import script
Reads the Baza sheets from sales Excel files and loads them into torb.db

Usage:
    python3 import_to_sqlite.py

Output:
    data/torb.db  — SQLite database with transactions table + indexes + views
"""

import sqlite3
import openpyxl
import os
from datetime import datetime, date

DB_PATH = "data/torb.db"
DOCS_PATH = "docs_input"

# Files to import, in order. Later files can add rows not in earlier ones.
# Deduplication is on (nr_dl, cod_produs, nr_factura).
SOURCES = [
    {
        "file": "vanzari_01.03.2026.xlsx",
        "sheet": "Baza",
        "desc": "Main sales data (2024 + 2025 + Jan-Feb 2026)",
    },
    {
        "file": "raport Dragos 31_03_2026.xlsx",
        "sheet": "Baza",
        "desc": "Dragos report — adds March 2026 data",
    },
]

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tranzactii (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Time
    luna            INTEGER,        -- month (1-12)
    an              INTEGER,        -- year
    data_dl         TEXT,           -- delivery date (ISO)

    -- Document references
    nr_dl           TEXT,           -- delivery note number
    nr_factura      TEXT,           -- invoice number (factout)
    nr_comanda      TEXT,           -- order number

    -- Product
    cod_produs      TEXT,           -- product code
    sku             TEXT,           -- full SKU name + barcode
    furnizor        TEXT,           -- brand (Basilur, Toras, Leonex, etc.)
    um              TEXT,           -- unit of measure

    -- Quantities & Financials (RON)
    cantitate       REAL,           -- quantity
    pret_vanzare    REAL,           -- unit selling price
    tva_pct         REAL,           -- VAT %
    pret_cumparare  REAL,           -- unit purchase price
    val_bruta       REAL,           -- gross value
    val_neta        REAL,           -- net value (main revenue figure)
    val_achizitie   REAL,           -- purchase value
    val_usd         REAL,           -- value in USD
    marja_bruta     REAL,           -- gross margin (RON)
    discount_pct    REAL,           -- discount %
    discount_val    REAL,           -- discount value

    -- Client
    client          TEXT,           -- client name
    cod_client      TEXT,           -- client code
    cui_client      TEXT,           -- client VAT/CUI
    tip_client      TEXT,           -- client type
    oras_client     TEXT,           -- client city
    judet_client    TEXT,           -- client county
    adresa_client   TEXT,           -- client address

    -- Agent / Channel
    agent           TEXT,           -- sales agent or channel (EMAG, SITE, etc.)

    -- Location
    adr_livrare     TEXT,           -- delivery address
    locatie         TEXT,           -- warehouse/location

    -- Dedup key: include pret_vanzare so that free promo lines (pvanz=0)
    -- and paid lines for the same product/invoice are stored separately.
    UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare)
)
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_an_luna     ON tranzactii(an, luna)",
    "CREATE INDEX IF NOT EXISTS idx_client      ON tranzactii(client)",
    "CREATE INDEX IF NOT EXISTS idx_furnizor    ON tranzactii(furnizor)",
    "CREATE INDEX IF NOT EXISTS idx_agent       ON tranzactii(agent)",
    "CREATE INDEX IF NOT EXISTS idx_data_dl     ON tranzactii(data_dl)",
    "CREATE INDEX IF NOT EXISTS idx_cod_produs  ON tranzactii(cod_produs)",
    "CREATE INDEX IF NOT EXISTS idx_judet       ON tranzactii(judet_client)",
    # Covering indexes for /products page (brands + top SKU queries)
    "CREATE INDEX IF NOT EXISTS idx_cov_brands ON tranzactii(an, luna, furnizor, cod_client, val_neta, marja_bruta, client, cod_produs)",
    "CREATE INDEX IF NOT EXISTS idx_cov_skus   ON tranzactii(an, luna, sku, furnizor, cod_client, val_neta, marja_bruta, cantitate, client)",
    # Index for v_sku_cod view lookups (sku → cod_produs mapping)
    "CREATE INDEX IF NOT EXISTS idx_sku_cod    ON tranzactii(sku, cod_produs)",
]

VIEWS = [
    # Monthly sales by brand
    """
    CREATE VIEW IF NOT EXISTS v_vanzari_luna_furnizor AS
    SELECT
        an, luna,
        furnizor,
        ROUND(SUM(val_neta), 2)       AS val_neta,
        ROUND(SUM(marja_bruta), 2)    AS marja_bruta,
        ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 2) AS marja_pct,
        SUM(cantitate)                AS cantitate
    FROM tranzactii
    GROUP BY an, luna, furnizor
    """,

    # Monthly sales by agent
    """
    CREATE VIEW IF NOT EXISTS v_vanzari_luna_agent AS
    SELECT
        an, luna,
        agent,
        ROUND(SUM(val_neta), 2)       AS val_neta,
        ROUND(SUM(marja_bruta), 2)    AS marja_bruta,
        ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 2) AS marja_pct
    FROM tranzactii
    GROUP BY an, luna, agent
    """,

    # Monthly sales by client
    """
    CREATE VIEW IF NOT EXISTS v_vanzari_luna_client AS
    SELECT
        an, luna,
        client, cod_client, tip_client, oras_client, judet_client,
        ROUND(SUM(val_neta), 2)       AS val_neta,
        ROUND(SUM(marja_bruta), 2)    AS marja_bruta,
        ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 2) AS marja_pct
    FROM tranzactii
    GROUP BY an, luna, client
    """,

    # Annual summary by brand
    """
    CREATE VIEW IF NOT EXISTS v_vanzari_an_furnizor AS
    SELECT
        an,
        furnizor,
        ROUND(SUM(val_neta), 2)       AS val_neta,
        ROUND(SUM(val_achizitie), 2)  AS val_achizitie,
        ROUND(SUM(marja_bruta), 2)    AS marja_bruta,
        ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 2) AS marja_pct,
        COUNT(DISTINCT client)        AS nr_clienti,
        COUNT(DISTINCT cod_produs)    AS nr_sku
    FROM tranzactii
    GROUP BY an, furnizor
    """,

    # Top SKUs by year
    """
    CREATE VIEW IF NOT EXISTS v_top_sku AS
    SELECT
        an,
        furnizor,
        cod_produs,
        sku,
        ROUND(SUM(val_neta), 2)    AS val_neta,
        ROUND(SUM(marja_bruta), 2) AS marja_bruta,
        SUM(cantitate)             AS cantitate,
        COUNT(DISTINCT client)     AS nr_clienti
    FROM tranzactii
    GROUP BY an, furnizor, cod_produs, sku
    """,

    # Client last order + activity status
    """
    CREATE VIEW IF NOT EXISTS v_clienti AS
    SELECT
        client,
        cod_client,
        cui_client,
        tip_client,
        oras_client,
        judet_client,
        MIN(data_dl)                       AS prima_comanda,
        MAX(data_dl)                       AS ultima_comanda,
        ROUND(SUM(val_neta), 2)            AS val_neta_total,
        ROUND(SUM(marja_bruta), 2)         AS marja_totala,
        COUNT(DISTINCT nr_factura)         AS nr_facturi,
        COUNT(DISTINCT furnizor)           AS nr_branduri,
        agent                              AS agent_principal
    FROM tranzactii
    GROUP BY client
    """,
]


# --- Column mapping per source file ---
# Maps source column name → canonical name used in DB
# (handles minor differences between the two Baza sheets)

COL_MAP = {
    # vanzari_01.03.2026.xlsx
    "Luna":         "luna",
    "An":           "an",
    "datadl":       "data_dl",
    "nrdl":         "nr_dl",
    "cantit":       "cantitate",
    "pvanz":        "pret_vanzare",
    "tva":          "tva_pct",
    "pcump":        "pret_cumparare",
    "Val_B":        "val_bruta",
    "Val_Net":      "val_neta",
    "Val_Achiz":    "val_achizitie",
    "Value USD":    "val_usd",
    "Marja_B":      "marja_bruta",
    "Client":       "client",
    "factout":      "nr_factura",
    "numeag":       "agent",
    "procent":      "discount_pct",
    "adr_livr":     "adr_livrare",
    "nrcomandam":   "nr_comanda",
    "codprod":      "cod_produs",
    "SKU":          "sku",
    "Furnizor":     "furnizor",
    "discount":     "discount_val",
    "codcli":       "cod_client",
    "adresa":       "adresa_client",
    "locatie":      "locatie",
    "numetipcli":   "tip_client",
    "cfcli":        "cui_client",
    "localcli":     "oras_client",
    "judet":        "judet_client",
    "um":           "um",

    # raport Dragos — slight name differences
    "luna":         "luna",
    "Val Brut":     "val_bruta",
    "Val Neta":     "val_neta",
    "Maja Bruta":   "marja_bruta",
}

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


def normalize_date(val):
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    return str(val)


def normalize_str(val):
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def normalize_num(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def read_baza(filepath, sheetname):
    print(f"  Reading {filepath} / {sheetname} ...")
    wb = openpyxl.load_workbook(filepath, data_only=True, read_only=True)
    ws = wb[sheetname]

    header = None
    rows_out = []

    for raw_row in ws.iter_rows(values_only=True):
        if not any(c is not None for c in raw_row):
            continue

        if header is None:
            header = [COL_MAP.get(str(c).strip(), str(c).strip()) if c is not None else None
                      for c in raw_row]
            continue

        row_dict = dict(zip(header, raw_row))

        record = {}
        for col in DB_COLS:
            val = row_dict.get(col)
            if col == "data_dl":
                record[col] = normalize_date(val)
            elif col in ("luna", "an", "cod_client"):
                record[col] = int(val) if val is not None else None
            elif col in (
                "cantitate", "pret_vanzare", "tva_pct", "pret_cumparare",
                "val_bruta", "val_neta", "val_achizitie", "val_usd",
                "marja_bruta", "discount_pct", "discount_val",
            ):
                record[col] = normalize_num(val)
            else:
                record[col] = normalize_str(val)

        rows_out.append(record)

    wb.close()
    print(f"    → {len(rows_out):,} data rows read")
    return rows_out


def insert_rows(conn, rows):
    placeholders = ", ".join(["?" for _ in DB_COLS])
    col_names = ", ".join(DB_COLS)
    sql = f"""
        INSERT OR IGNORE INTO tranzactii ({col_names})
        VALUES ({placeholders})
    """
    data = [[r[c] for c in DB_COLS] for r in rows]
    cursor = conn.cursor()
    cursor.executemany(sql, data)
    inserted = cursor.rowcount
    conn.commit()
    return inserted


def main():
    os.makedirs("data", exist_ok=True)

    print(f"\nCreating database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)

    print("Creating table...")
    conn.execute(CREATE_TABLE)

    print("Creating indexes...")
    for idx in INDEXES:
        conn.execute(idx)

    print("Creating views...")
    for view in VIEWS:
        conn.execute(view)

    conn.commit()

    total_inserted = 0
    for source in SOURCES:
        filepath = os.path.join(DOCS_PATH, source["file"])
        if not os.path.exists(filepath):
            print(f"\n  SKIP (not found): {filepath}")
            continue

        print(f"\nImporting: {source['desc']}")
        rows = read_baza(filepath, source["sheet"])
        inserted = insert_rows(conn, rows)
        skipped = len(rows) - inserted
        print(f"    → Inserted: {inserted:,} | Skipped (duplicates): {skipped:,}")
        total_inserted += inserted

    # Summary
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tranzactii")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(data_dl), MAX(data_dl) FROM tranzactii")
    date_range = cursor.fetchone()

    cursor.execute("SELECT COUNT(DISTINCT furnizor) FROM tranzactii")
    n_brands = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT client) FROM tranzactii")
    n_clients = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT agent) FROM tranzactii")
    n_agents = cursor.fetchone()[0]

    print(f"\n{'='*50}")
    print(f"  Database: {DB_PATH}")
    print(f"  Total rows:    {total:,}")
    print(f"  Date range:    {date_range[0]} → {date_range[1]}")
    print(f"  Brands:        {n_brands}")
    print(f"  Clients:       {n_clients:,}")
    print(f"  Agents:        {n_agents}")
    print(f"{'='*50}\n")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
