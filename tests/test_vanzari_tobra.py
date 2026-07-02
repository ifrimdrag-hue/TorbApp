import importlib.util
import os
import sqlite3

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _migration_0013():
    return _load(
        os.path.join(ROOT, "migrations", "0013_20260702_vanzari_tobra.py"),
        "_migration_0013",
    )


EXPECTED_COLS = {
    "id", "data_dl", "nr_dl", "nr_factura", "cod_produs", "sku",
    "cantitate", "pret_cumparare", "pret_vanzare",
}


def test_migration_0013_creates_table_and_is_idempotent():
    conn = sqlite3.connect(":memory:")
    mig = _migration_0013()
    assert mig.VERSION == 13
    mig.up(conn)
    mig.up(conn)  # IF NOT EXISTS -- safe to re-apply
    cols = {r[1] for r in conn.execute("PRAGMA table_info(vanzari_tobra)")}
    assert cols == EXPECTED_COLS
    idx = {r[1] for r in conn.execute("PRAGMA index_list(vanzari_tobra)")}
    assert "idx_vanzari_tobra_cod_data" in idx


def test_rebuild_db_schema_matches_migration():
    rebuild = _load(os.path.join(ROOT, "etl", "rebuild_db.py"), "_rebuild_db")
    conn = sqlite3.connect(":memory:")
    conn.execute(rebuild.CREATE_VANZARI_TOBRA)
    conn.execute(rebuild.VANZARI_TOBRA_INDEX)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(vanzari_tobra)")}
    assert cols == EXPECTED_COLS
