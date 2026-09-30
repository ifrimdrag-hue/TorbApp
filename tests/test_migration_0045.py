import importlib.util
import os
import sqlite3

import pytest


def _load_migration():
    path = os.path.join(os.path.dirname(__file__), "..", "migrations",
                        "0045_20260930_celmar_order_qty_repair.py")
    spec = importlib.util.spec_from_file_location("mig_0045", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LINES = "SELECT cantitate_comandata, cantitate_baxuri, total_valuta FROM comenzi_furnizori_linii WHERE comanda_id = ? ORDER BY id"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE comenzi_furnizori (
        id INTEGER PRIMARY KEY, nr_comanda TEXT, furnizor TEXT, file_source TEXT, total_usd REAL)""")
    c.execute("""CREATE TABLE comenzi_furnizori_linii (
        id INTEGER PRIMARY KEY, comanda_id INTEGER, sku TEXT,
        cantitate_comandata INTEGER, units_per_carton INTEGER, cantitate_baxuri REAL,
        pret_valuta REAL, total_valuta REAL)""")
    c.executemany("INSERT INTO comenzi_furnizori VALUES (?,?,?,?,?)", [
        # Aug-2026 form imported with the shifted columns
        (1, "NEW_ORDER_30_12.08.2026", "Celmar", "NEW_ORDER_30_12.08.2026.xls", 60101.27),
        # legacy form, imported correctly
        (2, "Romania_New_Order_28", "Celmar", "Romania_New_Order_28.xls", 10224.0),
        # manual order (no file) and another supplier: never touched
        (3, "MANUAL-1", "Celmar", None, 10.0),
        (4, "RO1-007-26", "Basilur", "RO1-007-26 PFI.xls", 10.0),
    ])
    # (comanda_id, sku, comandata, per_pallet, baxuri, pret, total) as stored by the import
    c.executemany(
        "INSERT INTO comenzi_furnizori_linii (comanda_id, sku, cantitate_comandata, units_per_carton,"
        " cantitate_baxuri, pret_valuta, total_valuta) VALUES (?,?,?,?,?,?,?)", [
            (1, "CELMAR MUSETEL", 39600, 3600, 36000.0, 1.1, 43560.0),
            (1, "CELMAR SOC CU LAMAIE", 4067, 3600, 3600.0, 1.13, 4595.71),
            (1, "CELMAR VERDE", 3600, 3600, 3600.0, 1.0, 3600.0),
            (1, "CELMAR MENTA 80 PLICURI", 3002, 1080, 1080.0, 2.78, 8345.56),
            (2, "CELMAR SUNATOARE", 7200, 3600, 2.0, 1.42, 10224.0),
            (3, "CELMAR VERDE", 10, 1, 10.0, 1.0, 10.0),
            (4, "B.EARL GREY", 10, 1, 10.0, 1.0, 10.0),
        ])
    return c


def test_repairs_lines_imported_with_shifted_columns(conn):
    _load_migration().up(conn)
    assert conn.execute(LINES, (1,)).fetchall() == [
        (36000, 10.0, 39600.0),
        (3600, 1.0, 4068.0),
        (3600, 1.0, 3600.0),
        (1080, 1.0, 3002.4),
    ]
    total = conn.execute("SELECT total_usd FROM comenzi_furnizori WHERE id = 1").fetchone()[0]
    assert total == pytest.approx(50270.4)


def test_leaves_correct_manual_and_other_supplier_orders_alone(conn):
    before = {cid: conn.execute(LINES, (cid,)).fetchall() for cid in (2, 3, 4)}
    _load_migration().up(conn)
    assert {cid: conn.execute(LINES, (cid,)).fetchall() for cid in (2, 3, 4)} == before
    assert conn.execute("SELECT total_usd FROM comenzi_furnizori WHERE id = 2").fetchone()[0] == 10224.0


def test_idempotent(conn):
    mig = _load_migration()
    mig.up(conn)
    once = conn.execute("SELECT * FROM comenzi_furnizori_linii ORDER BY id").fetchall()
    mig.up(conn)
    assert conn.execute("SELECT * FROM comenzi_furnizori_linii ORDER BY id").fetchall() == once
