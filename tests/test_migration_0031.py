import importlib.util
import os
import sqlite3

import pytest


def _load_migration():
    path = os.path.join(os.path.dirname(__file__), "..", "migrations",
                        "0031_20260707_auchan_cod_mare_identity.py")
    spec = importlib.util.spec_from_file_location("mig_0031", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


KL_AUCHAN = "KL EARL GREY (25X2G) 90204-4792252942417"
KL_ERP = "KL CEAI EARL GREY (25X2G) 90204-4792252942417"
GOPLANA = "C.GOPLANA JELEURI COACAZE 190G"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE tranzactii (
        cod_client TEXT, client TEXT, sku TEXT, cod_produs TEXT,
        furnizor TEXT, data_dl TEXT, nr_dl TEXT, nr_factura TEXT,
        val_neta REAL, UNIQUE(nr_dl, cod_produs, nr_factura))""")
    rows = [
        # Torb ERP: cod 1509 = Goplana/Celmar; cod 1661 = KL Earl Grey (ERP name)
        ("100", "ALT CLIENT", GOPLANA, "1509", "Celmar", "2026-05-01", "d1", "F1", 10),
        ("100", "ALT CLIENT", KL_ERP, "1661", "KingsLeaf", "2026-06-01", "d2", "F2", 20),
        # Auchan history (Tobra cod 1509 = KL Earl Grey, correct name)
        ("732", "AUCHAN", KL_AUCHAN, "1509", "KingsLeaf", "2026-05-10", "d3", "TOBRA1", 30),
        # July import bug: renamed to the Torb name for colliding cod 1509
        ("732", "AUCHAN", GOPLANA, "1509", "Celmar", "2026-07-02", "d4", "TOBRA2", 40),
        # Legitimate ERP rename case (same cod mare on both names) — untouched
        ("732", "AUCHAN", "B.BOUQUET ASSORTED (1.5GX25) 70197-4792252001121",
         "2001", "Basilur", "2026-03-01", "d5", "TOBRA3", 50),
        ("732", "AUCHAN", "B.CEAI BOUQUET ASSORTED (1.5GX25) 70197-4792252001121",
         "2001", "Basilur", "2026-06-15", "d6", "TOBRA4", 60),
        ("100", "ALT CLIENT", "B.CEAI BOUQUET ASSORTED (1.5GX25) 70197-4792252001121",
         "2001", "Basilur", "2026-06-20", "d7", "F3", 70),
    ]
    c.executemany("INSERT INTO tranzactii VALUES (?,?,?,?,?,?,?,?,?)", rows)
    return c


def test_migration_repairs_collision_and_aligns_cod(conn):
    _load_migration().up(conn)

    # Step 1: the July row renamed to Goplana is restored to Auchan's KL name.
    restored = conn.execute(
        "SELECT sku, furnizor FROM tranzactii WHERE nr_factura='TOBRA2'"
    ).fetchone()
    assert restored[0] == KL_AUCHAN
    assert restored[1] == "KingsLeaf"

    # Step 2: Auchan KL rows adopt the Torb ERP cod (1661) via cod mare 90204.
    cods = {r[0] for r in conn.execute(
        "SELECT DISTINCT cod_produs FROM tranzactii "
        "WHERE cod_client='732' AND sku LIKE 'KL %'")}
    assert cods == {"1661"}

    # The genuine ERP-rename article (same cod mare) keeps both spellings.
    renames = conn.execute(
        "SELECT COUNT(DISTINCT sku) FROM tranzactii "
        "WHERE cod_client='732' AND sku LIKE '%70197%'").fetchone()[0]
    assert renames == 2

    # Non-Auchan rows untouched.
    assert conn.execute(
        "SELECT sku FROM tranzactii WHERE nr_factura='F1'"
    ).fetchone()[0] == GOPLANA


def test_migration_idempotent(conn):
    mig = _load_migration()
    mig.up(conn)
    before = conn.execute(
        "SELECT sku, cod_produs, furnizor FROM tranzactii ORDER BY nr_factura"
    ).fetchall()
    mig.up(conn)
    after = conn.execute(
        "SELECT sku, cod_produs, furnizor FROM tranzactii ORDER BY nr_factura"
    ).fetchall()
    assert before == after
