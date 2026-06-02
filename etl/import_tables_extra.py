"""
Torb Logistic — Extra tables import
Adds to data/torb.db:
  - echipa              : team structure (from 01_Echipa)
  - targeturi_kpi       : monthly KPI targets per employee (from 03_Targeturi_2026)
  - actuale_kpi         : monthly KPI actuals per employee (from 04_Actuale_2026)
  - targeturi_cantitativ: SKU-level quantity targets per client/agent (from Cantitativ_*.xlsx)

Usage:
    python3 import_tables_extra.py
"""

import sqlite3
import openpyxl
import os

DB_PATH = "data/torb.db"
DOCS_PATH = "docs_input"

# ── Schema ────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS echipa (
    employee_id             TEXT PRIMARY KEY,
    nume                    TEXT,
    rol                     TEXT,
    raporteaza_la_id        TEXT,
    activ                   INTEGER,
    bonus_target_lunar_ron  REAL,
    bonus_target_trim_ron   REAL,
    observatii              TEXT
);

CREATE TABLE IF NOT EXISTS targeturi_kpi (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    an                  INTEGER,
    luna                INTEGER,
    employee_id         TEXT,
    net_sales           REAL,
    gross_margin        REAL,
    active_clients      REAL,
    focus_mix           REAL,
    collections         REAL,
    promo_exec          REAL,
    forecast            REAL,
    strategic           REAL,
    pharma_sales        REAL,
    team_sales          REAL,
    team_margin         REAL,
    team_active_clients REAL,
    UNIQUE(an, luna, employee_id)
);

CREATE TABLE IF NOT EXISTS actuale_kpi (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    an                  INTEGER,
    luna                INTEGER,
    employee_id         TEXT,
    net_sales           REAL,
    gross_margin        REAL,
    active_clients      REAL,
    focus_mix           REAL,
    collections         REAL,
    promo_exec          REAL,
    forecast            REAL,
    strategic           REAL,
    pharma_sales        REAL,
    team_sales          REAL,
    team_margin         REAL,
    team_active_clients REAL,
    penalizare_erori_pct REAL,
    UNIQUE(an, luna, employee_id)
);

CREATE TABLE IF NOT EXISTS targeturi_cantitativ (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent       TEXT,
    client      TEXT,
    sku         TEXT,
    an          INTEGER,
    luna        INTEGER,
    cantitate   REAL,
    UNIQUE(agent, client, sku, an, luna)
);

CREATE INDEX IF NOT EXISTS idx_tkpi_emp   ON targeturi_kpi(employee_id, an, luna);
CREATE INDEX IF NOT EXISTS idx_akpi_emp   ON actuale_kpi(employee_id, an, luna);
CREATE INDEX IF NOT EXISTS idx_tcant_agent ON targeturi_cantitativ(agent, an);
CREATE INDEX IF NOT EXISTS idx_tcant_client ON targeturi_cantitativ(client, an);
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def num(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def read_rows(fname, sheet):
    wb = openpyxl.load_workbook(fname, data_only=True, read_only=True)
    ws = wb[sheet]
    rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
    wb.close()
    return rows

# ── Table: echipa ─────────────────────────────────────────────────────────────

def import_echipa(conn):
    print("\nImporting echipa ...")
    rows = read_rows(
        os.path.join(DOCS_PATH, "bonusare_torb_structura_echipa.xlsx"),
        "01_Echipa"
    )
    data = []
    for row in rows[1:]:  # skip header
        emp_id, nume, rol, raporteaza, activ, bonus_l, bonus_t, obs = row[:8]
        if not emp_id:
            continue
        data.append((
            str(emp_id).strip(),
            str(nume).strip() if nume else None,
            str(rol).strip() if rol else None,
            str(raporteaza).strip() if raporteaza else None,
            int(activ) if activ is not None else None,
            num(bonus_l),
            num(bonus_t),
            str(obs).strip() if obs else None,
        ))

    conn.executemany("""
        INSERT OR REPLACE INTO echipa VALUES (?,?,?,?,?,?,?,?)
    """, data)
    conn.commit()
    print(f"  → {len(data)} employees inserted")

# ── Table: targeturi_kpi ──────────────────────────────────────────────────────

def import_targeturi_kpi(conn):
    print("\nImporting targeturi_kpi ...")
    rows = read_rows(
        os.path.join(DOCS_PATH, "bonusare_torb_structura_echipa.xlsx"),
        "03_Targeturi_2026"
    )
    data = []
    for row in rows[1:]:
        an, luna, emp_id = row[0], row[1], row[2]
        if not emp_id:
            continue
        kpis = row[6:18]  # Net Sales .. Team Active Clients
        data.append((
            int(an), int(luna), str(emp_id).strip(),
            num(kpis[0]), num(kpis[1]), num(kpis[2]), num(kpis[3]),
            num(kpis[4]), num(kpis[5]), num(kpis[6]), num(kpis[7]),
            num(kpis[8]), num(kpis[9]), num(kpis[10]), num(kpis[11]),
        ))
    conn.executemany("""
        INSERT OR IGNORE INTO targeturi_kpi
        (an, luna, employee_id, net_sales, gross_margin, active_clients,
         focus_mix, collections, promo_exec, forecast, strategic,
         pharma_sales, team_sales, team_margin, team_active_clients)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, data)
    conn.commit()
    print(f"  → {len(data)} rows inserted")

# ── Table: actuale_kpi ────────────────────────────────────────────────────────

def import_actuale_kpi(conn):
    print("\nImporting actuale_kpi ...")
    rows = read_rows(
        os.path.join(DOCS_PATH, "bonusare_torb_structura_echipa.xlsx"),
        "04_Actuale_2026"
    )
    data = []
    for row in rows[1:]:
        an, luna, emp_id = row[0], row[1], row[2]
        if not emp_id:
            continue
        kpis = row[6:18]
        penalizare = row[18] if len(row) > 18 else None
        data.append((
            int(an), int(luna), str(emp_id).strip(),
            num(kpis[0]), num(kpis[1]), num(kpis[2]), num(kpis[3]),
            num(kpis[4]), num(kpis[5]), num(kpis[6]), num(kpis[7]),
            num(kpis[8]), num(kpis[9]), num(kpis[10]), num(kpis[11]),
            num(penalizare),
        ))
    conn.executemany("""
        INSERT OR IGNORE INTO actuale_kpi
        (an, luna, employee_id, net_sales, gross_margin, active_clients,
         focus_mix, collections, promo_exec, forecast, strategic,
         pharma_sales, team_sales, team_margin, team_active_clients,
         penalizare_erori_pct)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, data)
    conn.commit()
    print(f"  → {len(data)} rows inserted")

# ── Table: targeturi_cantitativ ───────────────────────────────────────────────

CANTITATIV_FILES = [
    ("Cantitativ_Bogdan2026.xlsx",  "Bogdan Cantitativ",  "DRAGNEA BOGDAN"),
    ("Cantitativ_Oana2026.xlsx",    "Volum Oana",         "OANA FILIP"),
    ("Cantitativ_Claudiu2026.xlsx", "Volum Claudiu",      "BRINZA CLAUDIU"),
]

def import_targeturi_cantitativ(conn):
    print("\nImporting targeturi_cantitativ ...")
    total = 0

    for fname, sheet, agent_name in CANTITATIV_FILES:
        filepath = os.path.join(DOCS_PATH, fname)
        if not os.path.exists(filepath):
            print(f"  SKIP (not found): {filepath}")
            continue

        rows = read_rows(filepath, sheet)
        data = []

        current_client = None
        current_sku = None

        for row in rows[1:]:  # skip header
            client_cell, articol_cell, an_cell = row[0], row[1], row[2]
            months = row[3:15]  # columns 1-12

            # Client group header row (Articol=None, an=None)
            if client_cell and articol_cell is None and an_cell is None:
                current_client = str(client_cell).strip()
                current_sku = None
                continue

            # SKU row for year — articol may be set (2026 row) or None (2024/2025 inherit)
            if articol_cell:
                current_sku = str(articol_cell).strip()

            if not current_client or not current_sku or an_cell is None:
                continue

            an = int(an_cell)

            for luna_idx, qty in enumerate(months, start=1):
                q = num(qty)
                if q is not None and q != 0:
                    data.append((
                        agent_name, current_client, current_sku,
                        an, luna_idx, q
                    ))

        conn.executemany("""
            INSERT OR IGNORE INTO targeturi_cantitativ
            (agent, client, sku, an, luna, cantitate)
            VALUES (?,?,?,?,?,?)
        """, data)
        conn.commit()
        print(f"  {fname}: {len(data)} non-zero rows inserted")
        total += len(data)

    print(f"  → Total: {total} rows")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\nOpening database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)

    print("Creating tables and indexes ...")
    for stmt in DDL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()

    import_echipa(conn)
    import_targeturi_kpi(conn)
    import_actuale_kpi(conn)
    import_targeturi_cantitativ(conn)

    # Summary
    print("\n" + "="*50)
    for table in ["echipa", "targeturi_kpi", "actuale_kpi", "targeturi_cantitativ"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<28} {count:>6} rows")
    print("="*50)

    conn.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
