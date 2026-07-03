"""
Rebuild complet al bazei de date Torb din fișierele ERP curente.

Șterge DB-ul existent, recreează schema și reimportă toate datele.
Folosiți când datele din DB sunt incorecte (ex: cantități greșite, val_neta
negativă pe linii gratuite din promotii 10+1).

Usage:
    python rebuild_db.py
    python rebuild_db.py --vanzari "docs_input/rapoarte/Vanzari 10.05.2026.xlsx"
"""

import sys
import os
import shutil
import sqlite3
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Allow dynamic imports of sibling ETL modules (import_vanzari_erp, update_data, etc.)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DB_PATH = "data/torb.db"
DOCS_PATH = "docs_input"

# Schema din import_to_sqlite — recreata identic
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS tranzactii (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    luna            INTEGER,
    an              INTEGER,
    data_dl         TEXT,
    nr_dl           TEXT,
    nr_factura      TEXT,
    nr_comanda      TEXT,
    cod_produs      TEXT,
    sku             TEXT,
    furnizor        TEXT,
    um              TEXT,
    cantitate       REAL,
    pret_vanzare    REAL,
    tva_pct         REAL,
    pret_cumparare  REAL,
    val_bruta       REAL,
    val_neta        REAL,
    val_achizitie   REAL,
    val_usd         REAL,
    marja_bruta     REAL,
    discount_pct    REAL,
    discount_val    REAL,
    client          TEXT,
    cod_client      TEXT,
    cui_client      TEXT,
    tip_client      TEXT,
    oras_client     TEXT,
    judet_client    TEXT,
    adresa_client   TEXT,
    agent           TEXT,
    adr_livrare     TEXT,
    locatie         TEXT,
    -- Include pret_vanzare so free promo lines and paid lines stay separate
    UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare)
)
"""

# Cost table for the Auchan import (migration 0013). NOT dropped on rebuild:
# cost history persists; INSERT OR IGNORE in import_vanzari_erp.py dedups.
CREATE_VANZARI_TOBRA = """
CREATE TABLE IF NOT EXISTS vanzari_tobra (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    data_dl        TEXT,
    nr_dl          TEXT,
    nr_factura     TEXT,
    cod_produs     TEXT,
    sku            TEXT,
    cantitate      REAL,
    pret_cumparare REAL,
    pret_vanzare   REAL,
    UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare)
)
"""

VANZARI_TOBRA_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_vanzari_tobra_cod_data"
    " ON vanzari_tobra(cod_produs, data_dl)"
)

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_an_luna     ON tranzactii(an, luna)",
    "CREATE INDEX IF NOT EXISTS idx_client      ON tranzactii(client)",
    "CREATE INDEX IF NOT EXISTS idx_furnizor    ON tranzactii(furnizor)",
    "CREATE INDEX IF NOT EXISTS idx_agent       ON tranzactii(agent)",
    "CREATE INDEX IF NOT EXISTS idx_data_dl     ON tranzactii(data_dl)",
    "CREATE INDEX IF NOT EXISTS idx_cod_produs  ON tranzactii(cod_produs)",
    "CREATE INDEX IF NOT EXISTS idx_judet       ON tranzactii(judet_client)",
]

VIEWS = [
    """
    CREATE VIEW IF NOT EXISTS v_sku_cod AS
    SELECT sku, cod_produs AS cod
    FROM tranzactii
    WHERE sku IS NOT NULL AND cod_produs IS NOT NULL
    GROUP BY sku
    """,
    """
    CREATE VIEW IF NOT EXISTS v_vanzari_luna_furnizor AS
    SELECT an, luna, furnizor,
        ROUND(SUM(val_neta), 2)       AS val_neta,
        ROUND(SUM(marja_bruta), 2)    AS marja_bruta,
        ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 2) AS marja_pct,
        SUM(cantitate)                AS cantitate
    FROM tranzactii GROUP BY an, luna, furnizor
    """,
    """
    CREATE VIEW IF NOT EXISTS v_vanzari_luna_agent AS
    SELECT an, luna, agent,
        ROUND(SUM(val_neta), 2)       AS val_neta,
        ROUND(SUM(marja_bruta), 2)    AS marja_bruta,
        ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 2) AS marja_pct
    FROM tranzactii GROUP BY an, luna, agent
    """,
    """
    CREATE VIEW IF NOT EXISTS v_vanzari_luna_client AS
    SELECT an, luna, client, cod_client, tip_client, oras_client, judet_client,
        ROUND(SUM(val_neta), 2)       AS val_neta,
        ROUND(SUM(marja_bruta), 2)    AS marja_bruta,
        ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 2) AS marja_pct
    FROM tranzactii GROUP BY an, luna, client
    """,
    """
    CREATE VIEW IF NOT EXISTS v_vanzari_an_furnizor AS
    SELECT an, furnizor,
        ROUND(SUM(val_neta), 2)       AS val_neta,
        ROUND(SUM(val_achizitie), 2)  AS val_achizitie,
        ROUND(SUM(marja_bruta), 2)    AS marja_bruta,
        ROUND(SUM(marja_bruta) * 100.0 / NULLIF(SUM(val_neta), 0), 2) AS marja_pct,
        COUNT(DISTINCT client)        AS nr_clienti,
        COUNT(DISTINCT cod_produs)    AS nr_sku
    FROM tranzactii GROUP BY an, furnizor
    """,
    """
    CREATE VIEW IF NOT EXISTS v_top_sku AS
    SELECT an, furnizor, cod_produs, sku,
        ROUND(SUM(val_neta), 2)    AS val_neta,
        ROUND(SUM(marja_bruta), 2) AS marja_bruta,
        SUM(cantitate)             AS cantitate,
        COUNT(DISTINCT client)     AS nr_clienti
    FROM tranzactii GROUP BY an, furnizor, cod_produs, sku
    """,
    """
    CREATE VIEW IF NOT EXISTS v_clienti AS
    SELECT client, cod_client, cui_client, tip_client, oras_client, judet_client,
        MIN(data_dl)                       AS prima_comanda,
        MAX(data_dl)                       AS ultima_comanda,
        ROUND(SUM(val_neta), 2)            AS val_neta_total,
        ROUND(SUM(marja_bruta), 2)         AS marja_totala,
        COUNT(DISTINCT nr_factura)         AS nr_facturi,
        COUNT(DISTINCT furnizor)           AS nr_branduri,
        (SELECT t2.agent FROM tranzactii t2
         WHERE t2.client = t1.client
         ORDER BY t2.data_dl DESC, t2.rowid DESC
         LIMIT 1)                          AS agent_principal
    FROM tranzactii t1
    GROUP BY t1.client
    """,
]


def find_vanzari_file():
    """Cauta Vanzari*.xlsx in docs_input/rapoarte/ (cel mai recent dupa data din nume)."""
    rapoarte = os.path.join(DOCS_PATH, "rapoarte")
    candidates = []
    if os.path.isdir(rapoarte):
        for f in os.listdir(rapoarte):
            if f.lower().startswith("vanzari") and f.lower().endswith((".xlsx", ".xls")):
                candidates.append(os.path.join(rapoarte, f))
    # Fallback: foldere datate DD.MM.YYYY
    import re
    date_pattern = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
    from datetime import date as ddate
    dated = []
    for entry in os.listdir(DOCS_PATH):
        if date_pattern.match(entry) and os.path.isdir(os.path.join(DOCS_PATH, entry)):
            folder = os.path.join(DOCS_PATH, entry)
            for f in os.listdir(folder):
                if f.lower().startswith("vanzari") and f.lower().endswith((".xlsx", ".xls")):
                    day, month, year = entry.split(".")
                    dated.append((ddate(int(year), int(month), int(day)),
                                  os.path.join(folder, f)))
    if dated:
        dated.sort(reverse=True)
        candidates.insert(0, dated[0][1])
    return candidates[0] if candidates else None


def backup_db(keep=3):
    if not os.path.exists(DB_PATH):
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{DB_PATH}.bak.{ts}"
    shutil.copy2(DB_PATH, backup)
    print(f"  → Backup: {backup}")
    data_dir = os.path.dirname(DB_PATH)
    baks = sorted(
        [f for f in os.listdir(data_dir) if f.startswith("torb.db.bak.")],
        reverse=True,
    )
    for old in baks[keep:]:
        try:
            os.remove(os.path.join(data_dir, old))
            print(f"  → Backup vechi șters: {old}")
        except OSError:
            pass
    return backup


def reset_tranzactii(conn):
    """Sterge si recreeaza doar tabelele de date (tranzactii + stoc).
    Pastreaza tabelele de configurare: conditii_comerciale, produse,
    preturi_vanzare, costuri_landing, etc."""
    conn.execute("DROP TABLE IF EXISTS tranzactii")
    conn.execute("DROP TABLE IF EXISTS stoc")
    # Sterge si view-urile — vor fi recreate
    for v in ("v_vanzari_luna_furnizor", "v_vanzari_luna_agent",
              "v_vanzari_luna_client", "v_vanzari_an_furnizor",
              "v_top_sku", "v_clienti"):
        conn.execute(f"DROP VIEW IF EXISTS {v}")
    conn.execute(CREATE_TABLE)
    conn.execute(CREATE_VANZARI_TOBRA)
    conn.execute(VANZARI_TOBRA_INDEX)
    for idx in INDEXES:
        conn.execute(idx)
    for view in VIEWS:
        conn.execute(view)
    conn.commit()
    print("  → tranzactii + stoc resetate; tabele configurare păstrate")


def print_summary(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), MIN(data_dl), MAX(data_dl) FROM tranzactii")
    total, d_min, d_max = cur.fetchone()
    cur.execute("SELECT COUNT(DISTINCT furnizor) FROM tranzactii")
    n_brands = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT client) FROM tranzactii")
    n_clients = cur.fetchone()[0]
    cur.execute("""
        SELECT furnizor, COUNT(*) as linii, ROUND(SUM(val_neta),0) as vn
        FROM tranzactii GROUP BY furnizor ORDER BY vn DESC
    """)
    brands = cur.fetchall()
    print(f"\n{'='*55}")
    print(f"  Tranzacții totale : {total:,}")
    print(f"  Interval date     : {d_min} → {d_max}")
    print(f"  Clienți distincți : {n_clients:,}")
    print(f"  Branduri          : {n_brands}")
    print(f"  {'Brand':<15} {'Linii':>8} {'Val Netă (RON)':>16}")
    for b, cnt, v in brands:
        print(f"  {(b or 'N/A'):<15} {cnt:>8,} {(v or 0):>16,.0f}")
    print(f"{'='*55}")


def main(vanzari_file=None):
    # Parse --vanzari argument (ignored if vanzari_file passed directly)
    if vanzari_file is None and "--vanzari" in sys.argv:
        idx = sys.argv.index("--vanzari")
        if idx + 1 < len(sys.argv):
            vanzari_file = sys.argv[idx + 1]

    print("=" * 55)
    print("  Torb — Rebuild complet bază de date")
    print("=" * 55)

    # Detectare fisier vanzari
    if vanzari_file is None:
        vanzari_file = find_vanzari_file()
    if vanzari_file is None:
        print("EROARE: Nu am găsit niciun fișier Vanzari*.xlsx.")
        print("Folosiți: python rebuild_db.py --vanzari <cale_fisier.xlsx>")
        sys.exit(1)
    print(f"\n  Fișier vânzări: {vanzari_file}")

    # 1. Backup + reset tabele date (pastreaza configurare)
    print("\n[1] Backup + reset tranzactii/stoc...")
    os.makedirs("data", exist_ok=True)
    backup_db()
    conn = sqlite3.connect(DB_PATH)
    reset_tranzactii(conn)
    conn.close()

    # 3. Import vanzari ERP (cu discproc_p aplicat)
    print("\n[3] Import vânzări ERP...")
    import import_vanzari_erp
    import_vanzari_erp.run(vanzari_file)

    # 4. Import Tobra → Auchan
    print("\n[4] Import Tobra → Auchan...")
    tobra_dir = os.path.join(DOCS_PATH, "rapoarte")
    tobra_file = None
    if os.path.isdir(tobra_dir):
        for f in os.listdir(tobra_dir):
            fl = f.lower()
            if fl.endswith((".xls", ".xlsx")) and "auchan" in fl:
                tobra_file = os.path.join(tobra_dir, f)
                break
    if tobra_file:
        import import_vanzari_tobra_auchan
        import_vanzari_tobra_auchan.run(tobra_file)
    else:
        print("  SKIP: nu există fișier tobra-auchan în rapoarte/")

    # 4b. Merge Profi Rom Food → Mega Image (achizitie)
    print("\n[4b] Merge Profi Rom Food → Mega Image...")
    import merge_client_profi_mega
    merge_conn = sqlite3.connect(DB_PATH)
    merge_client_profi_mega.run(merge_conn)
    merge_conn.close()

    # 5. Import stoc
    print("\n[5] Import stoc...")
    rapoarte = os.path.join(DOCS_PATH, "rapoarte")
    stoc_file = None
    if os.path.isdir(rapoarte):
        for f in os.listdir(rapoarte):
            if f.lower().startswith("stoc") and f.lower().endswith((".xls", ".xlsx")):
                stoc_file = os.path.join(rapoarte, f)
                break
    if stoc_file:
        import import_stoc
        import_stoc.run(stoc_file)
    else:
        print("  SKIP: nu există fișier stoc în rapoarte/")

    # 6a. Asigura toate tabelele de configurare (CREATE IF NOT EXISTS — nu atinge datele existente)
    print("\n[6a] Tabele configurare...")
    cfg_conn = sqlite3.connect(DB_PATH)
    cfg_conn.executescript("""
        CREATE TABLE IF NOT EXISTS conditii_comerciale (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            an            INTEGER NOT NULL,
            cod_client    TEXT,
            furnizor      TEXT,
            tip_valoare   TEXT NOT NULL CHECK(tip_valoare IN ('pct','suma_fixa')),
            periodicitate TEXT NOT NULL CHECK(periodicitate IN ('lunar','anual','unic')),
            valoare       REAL NOT NULL,
            descriere     TEXT,
            data_creare   TEXT
        );
        CREATE TABLE IF NOT EXISTS termene_plata (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            an          INTEGER NOT NULL,
            cod_client  TEXT NOT NULL,
            zile_termen INTEGER NOT NULL,
            observatii  TEXT,
            data_creare TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_cc_an_client ON conditii_comerciale(an, cod_client);
        CREATE INDEX IF NOT EXISTS idx_tp_an_client ON termene_plata(an, cod_client);

        CREATE TABLE IF NOT EXISTS produse (
            sku           TEXT PRIMARY KEY,
            descriere     TEXT,
            furnizor      TEXT,
            brand         TEXT,
            categorie     TEXT,
            gramaj        REAL,
            buc_cutie     INTEGER,
            ean           TEXT,
            tva_pct       REAL DEFAULT 0.09,
            hs_code       TEXT,
            taxa_vamala_mfn_pct  REAL DEFAULT 0,
            taxa_vamala_pct      REAL DEFAULT 0,
            origine       TEXT DEFAULT 'import_extraeu',
            tara_origine  TEXT,
            activ         INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS rate_schimb (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            an        INTEGER NOT NULL,
            moneda    TEXT NOT NULL,
            curs_ron  REAL NOT NULL,
            UNIQUE(an, moneda)
        );
        CREATE TABLE IF NOT EXISTS costuri_landing (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            an                    INTEGER NOT NULL,
            sku                   TEXT NOT NULL,
            moneda                TEXT NOT NULL DEFAULT 'USD',
            pret_achizitie_valuta REAL,
            curs_ron              REAL,
            pret_achizitie_ron    REAL,
            transport_pct         REAL DEFAULT 10.0,
            taxa_vamala_pct       REAL DEFAULT 0.0,
            alte_costuri_ron      REAL DEFAULT 0.0,
            landing_cost_ron      REAL,
            UNIQUE(an, sku)
        );
        CREATE TABLE IF NOT EXISTS preturi_vanzare (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            an              INTEGER NOT NULL,
            sku             TEXT NOT NULL,
            cod_client      TEXT,
            pret_vanzare_ron REAL NOT NULL,
            activ           INTEGER DEFAULT 1,
            UNIQUE(an, sku, cod_client)
        );
        CREATE INDEX IF NOT EXISTS idx_pv_sku ON preturi_vanzare(sku);
        CREATE INDEX IF NOT EXISTS idx_cl_sku ON costuri_landing(sku);

        CREATE TABLE IF NOT EXISTS termene_aprovizionare (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            furnizor        TEXT    NOT NULL,
            zile_livrare    INTEGER NOT NULL DEFAULT 30,
            sezon_craciun   INTEGER NOT NULL DEFAULT 0,
            observatii      TEXT,
            UNIQUE(furnizor)
        );
        CREATE TABLE IF NOT EXISTS comenzi_furnizori (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            nr_comanda                  TEXT,
            furnizor                    TEXT    NOT NULL,
            data_comanda                DATE    NOT NULL DEFAULT (date('now')),
            status                      TEXT    NOT NULL DEFAULT 'draft',
            data_estimata_livrare       DATE,
            data_confirmare_furnizor    DATE,
            observatii                  TEXT,
            created_at                  DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at                  DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS comenzi_furnizori_linii (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            comanda_id              INTEGER NOT NULL REFERENCES comenzi_furnizori(id) ON DELETE CASCADE,
            sku                     TEXT    NOT NULL,
            cantitate_sugerat       INTEGER DEFAULT 0,
            cantitate_comandata     INTEGER NOT NULL DEFAULT 0,
            cantitate_ro            INTEGER DEFAULT 0,
            cantitate_export        INTEGER DEFAULT 0,
            cantitate_confirmata    INTEGER,
            cod_furnizor            TEXT,
            units_per_carton        INTEGER,
            cantitate_baxuri        REAL,
            gross_kg                REAL,
            net_kg                  REAL,
            cbm                     REAL,
            total_valuta            REAL,
            descriere               TEXT,
            pret_valuta             REAL,
            moneda                  TEXT    DEFAULT 'EUR',
            observatii              TEXT
        );
        CREATE TABLE IF NOT EXISTS corr_leonex_cod_mapping (
            cod_furnizor TEXT PRIMARY KEY,
            cod_torb     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clienti_export (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cod_client  TEXT NOT NULL UNIQUE,
            client      TEXT,
            tara        TEXT,
            activ       INTEGER DEFAULT 1,
            observatii  TEXT
        );

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
        CREATE INDEX IF NOT EXISTS idx_tkpi_emp    ON targeturi_kpi(employee_id, an, luna);
        CREATE INDEX IF NOT EXISTS idx_akpi_emp    ON actuale_kpi(employee_id, an, luna);
        CREATE INDEX IF NOT EXISTS idx_tcant_agent ON targeturi_cantitativ(agent, an);
        CREATE INDEX IF NOT EXISTS idx_tcant_client ON targeturi_cantitativ(client, an);
    """)
    # Seed lead times (INSERT OR IGNORE — nu suprascrie datele existente)
    for furnizor, zile, sezon, obs in [
        ('Basilur',    120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai'),
        ('KingsLeaf',  120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai'),
        ('Tipson',     120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai'),
        ('Organsia',   120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai'),
        ('Toras',       45, 0, None),
        ('Delaviuda',   30, 0, None),
        ('Celmar',      30, 0, None),
        ('Leonex',      30, 0, None),
    ]:
        cfg_conn.execute(
            "INSERT OR IGNORE INTO termene_aprovizionare (furnizor, zile_livrare, sezon_craciun, observatii)"
            " VALUES (?, ?, ?, ?)", (furnizor, zile, sezon, obs)
        )
    # Seed Leonex supplier-code -> Cod TORB mapping (INSERT OR IGNORE)
    for cod_furnizor, cod_torb in [
        ('MK001730', '1683'), ('MK001728', '1571'), ('MK000928', '584'),
        ('MK001731', '1574'), ('MK000497', '580'),  ('MK000493', '579'),
        ('MK000927', '978'),  ('MK001729', '1570'), ('MK000929', '583'),
        ('MK001899', '1701'),
    ]:
        cfg_conn.execute(
            "INSERT OR IGNORE INTO corr_leonex_cod_mapping (cod_furnizor, cod_torb) VALUES (?, ?)",
            (cod_furnizor, cod_torb)
        )
    # Migrare coloane lipsă din comenzi_furnizori_linii (schema evolutivă)
    extra_cols = [
        ('cantitate_ro',     'INTEGER DEFAULT 0'),
        ('cantitate_export', 'INTEGER DEFAULT 0'),
        ('cod_furnizor',     'TEXT'),
        ('units_per_carton', 'INTEGER'),
        ('cantitate_baxuri', 'REAL'),
        ('gross_kg',         'REAL'),
        ('net_kg',           'REAL'),
        ('cbm',              'REAL'),
        ('total_valuta',     'REAL'),
        ('descriere',        'TEXT'),
    ]
    existing_cols = {r[1] for r in cfg_conn.execute('PRAGMA table_info(comenzi_furnizori_linii)').fetchall()}
    for col, typedef in extra_cols:
        if col not in existing_cols:
            cfg_conn.execute(f'ALTER TABLE comenzi_furnizori_linii ADD COLUMN {col} {typedef}')
    cfg_conn.commit()
    cfg_conn.close()
    print("  → toate tabelele de configurare OK")

    # 6b. Import echipa + KPI din bonusare_torb_structura_echipa.xlsx
    print("\n[6b] Import echipă + KPI...")
    try:
        import import_tables_extra
        import importlib
        importlib.reload(import_tables_extra)
        extra_conn = sqlite3.connect(DB_PATH)
        import_tables_extra.import_echipa(extra_conn)
        import_tables_extra.import_targeturi_kpi(extra_conn)
        import_tables_extra.import_actuale_kpi(extra_conn)
        import_tables_extra.import_targeturi_cantitativ(extra_conn)
        extra_conn.close()
    except Exception as e:
        print(f"  SKIP import echipa/KPI: {e}")

    # 6c. Import comenzi în tranzit (Basilur + Toras)
    print("\n[6c] Import comenzi furnizori în tranzit...")
    try:
        import import_comenzi_tranzit_basilur
        import import_comenzi_tranzit_toras
        importlib.reload(import_comenzi_tranzit_basilur)
        importlib.reload(import_comenzi_tranzit_toras)
        import_comenzi_tranzit_basilur.run()
        import_comenzi_tranzit_toras.run()
    except Exception as e:
        print(f"  SKIP import comenzi tranzit: {e}")

    # 6. Asignare gama + reconciliere stoc
    print("\n[6] Asignare gama + reconciliere stoc...")
    import update_data
    conn = sqlite3.connect(DB_PATH)
    try:
        update_data.ensure_gama_column(conn)
        update_data.assign_gama(conn)
        update_data.assign_gama_tranzactii(conn)
        conn.commit()
    except Exception as e:
        print(f"  SKIP gama produse: {e} (tabelul produse nu există — rulează init_produse separat)")

    # Reconciliere stoc Altele
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE stoc SET
                furnizor = (SELECT t.furnizor FROM tranzactii t
                            WHERE t.cod_produs = stoc.cod_produs
                              AND t.furnizor IS NOT NULL AND t.furnizor != 'Altele' LIMIT 1),
                gama     = (SELECT t.furnizor FROM tranzactii t
                            WHERE t.cod_produs = stoc.cod_produs
                              AND t.furnizor IS NOT NULL AND t.furnizor != 'Altele' LIMIT 1)
            WHERE furnizor = 'Altele' AND cod_produs IN (
                SELECT DISTINCT cod_produs FROM tranzactii
                WHERE furnizor IS NOT NULL AND furnizor != 'Altele'
            )
        """)
        if cur.rowcount:
            print(f"  → Stoc reasignat: {cur.rowcount} rânduri")
        conn.commit()
    except Exception as e:
        print(f"  SKIP reconciliere stoc: {e}")

    # 7. Sumar final
    print("\n[7] Sumar final:")
    print_summary(conn)
    conn.close()

    print("\nREBUILD FINALIZAT.")


if __name__ == "__main__":
    main()
