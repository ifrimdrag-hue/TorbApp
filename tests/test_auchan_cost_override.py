import importlib.util
import os
import sqlite3

ETL = os.path.join(os.path.dirname(__file__), "..", "etl")


def _mod():
    path = os.path.join(ETL, "import_vanzari_tobra_auchan.py")
    spec = importlib.util.spec_from_file_location("_auchan_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _conn(cost_rows):
    """cost_rows: list of (data_dl, cod_produs, pret_cumparare)."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE vanzari_tobra ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " data_dl TEXT, nr_dl TEXT, nr_factura TEXT,"
        " cod_produs TEXT, sku TEXT,"
        " cantitate REAL, pret_cumparare REAL, pret_vanzare REAL,"
        " UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare))"
    )
    conn.executemany(
        "INSERT INTO vanzari_tobra (data_dl, nr_dl, cod_produs, pret_cumparare)"
        " VALUES (?, ?, ?, ?)",
        [(d, f"DL{i}", cod, p) for i, (d, cod, p) in enumerate(cost_rows)],
    )
    return conn


def _record(**kw):
    rec = {"cod_produs": "100", "data_dl": "2026-06-25", "cantitate": 10.0,
           "pret_cumparare": 3.0, "val_neta": 100.0,
           "val_achizitie": 30.0, "marja_bruta": 70.0}
    rec.update(kw)
    return rec


def test_window_average_is_simple_average():
    m = _mod()
    conn = _conn([("2026-06-10", "100", 5.0), ("2026-06-20", "100", 7.0)])
    assert m.lookup_tobra_cost(conn, "100", "2026-06-25") == (6.0, "window")


def test_window_includes_same_day():
    m = _mod()
    conn = _conn([("2026-07-02", "100", 4.0)])
    assert m.lookup_tobra_cost(conn, "100", "2026-07-02") == (4.0, "window")


def test_entry_exactly_30_days_old_falls_to_last_known():
    m = _mod()
    # window is (d-30, d]: 2026-06-02 == d-30 for d=2026-07-02 -> excluded
    conn = _conn([("2026-06-02", "100", 5.0)])
    assert m.lookup_tobra_cost(conn, "100", "2026-07-02") == (5.0, "last_known")


def test_last_known_averages_the_most_recent_day_only():
    m = _mod()
    conn = _conn([("2026-01-15", "100", 5.0), ("2026-01-15", "100", 6.0),
                  ("2026-01-01", "100", 9.0)])
    assert m.lookup_tobra_cost(conn, "100", "2026-06-25") == (5.5, "last_known")


def test_future_entries_are_ignored():
    m = _mod()
    conn = _conn([("2026-07-10", "100", 9.9)])
    assert m.lookup_tobra_cost(conn, "100", "2026-07-02") == (None, None)


def test_unknown_product_returns_none():
    m = _mod()
    conn = _conn([])
    assert m.lookup_tobra_cost(conn, "999", "2026-07-02") == (None, None)


def test_apply_override_recomputes_financials():
    m = _mod()
    conn = _conn([("2026-06-20", "100", 2.5)])
    rec = _record()
    counts = m.apply_cost_override(conn, [rec])
    assert rec["pret_cumparare"] == 2.5
    assert rec["val_achizitie"] == 25.0
    assert rec["marja_bruta"] == 75.0
    assert counts == {"window": 1, "last_known": 0, "excel": 0}


def test_apply_override_keeps_excel_value_without_data():
    m = _mod()
    conn = _conn([])
    rec = _record()
    counts = m.apply_cost_override(conn, [rec])
    assert rec["pret_cumparare"] == 3.0
    assert rec["val_achizitie"] == 30.0
    assert rec["marja_bruta"] == 70.0
    assert counts == {"window": 0, "last_known": 0, "excel": 1}


def test_apply_override_missing_cod_produs_uses_excel():
    m = _mod()
    conn = _conn([("2026-06-20", "100", 2.5)])
    rec = _record(cod_produs=None)
    counts = m.apply_cost_override(conn, [rec])
    assert rec["pret_cumparare"] == 3.0
    assert counts == {"window": 0, "last_known": 0, "excel": 1}
