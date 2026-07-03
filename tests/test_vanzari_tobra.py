import importlib.util
import os
import sqlite3
from datetime import datetime

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
    cols = {r[1] for r in conn.execute("PRAGMA table_info(corr_vanzari_tobra)")}
    assert cols == EXPECTED_COLS
    idx = {r[1] for r in conn.execute("PRAGMA index_list(corr_vanzari_tobra)")}
    assert "idx_corr_vanzari_tobra_cod_data" in idx


def test_rebuild_db_schema_matches_migration():
    rebuild = _load(os.path.join(ROOT, "etl", "rebuild_db.py"), "_rebuild_db")
    conn = sqlite3.connect(":memory:")
    conn.execute(rebuild.CREATE_VANZARI_TOBRA)
    conn.execute(rebuild.VANZARI_TOBRA_INDEX)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(corr_vanzari_tobra)")}
    assert cols == EXPECTED_COLS




def _erp():
    return _load(os.path.join(ROOT, "etl", "import_vanzari_erp.py"), "_erp_mod")


def _erp_raw_row(codcli, nrdl, codprod, pcump):
    return {
        "codcli": codcli, "datadl": datetime(2026, 6, 15), "nrdl": nrdl,
        "factout": "F1", "nrcomandam": None, "codprod": codprod,
        "den_b": "B.TEST TEA", "um": "BUC", "cantit": 5, "pvanz": 6.0,
        "tva": 9.0, "pcump": pcump, "discount": 0, "procent": 0,
        "den_a": "CLIENT X", "numeag": "AGENT X", "adresa": None,
        "locatie": None, "numetipcli": None, "cfcli": None,
        "localcli": None, "judet": None, "adr_livr": None,
    }


def test_process_rows_diverts_tobra_lines():
    erp = _erp()
    rows = [
        _erp_raw_row(719.0, "DL1", "100", 3.5),   # Torb->Tobra: diverted
        _erp_raw_row(100, "DL2", "200", 1.0),     # normal client: kept
    ]
    records, tobra = erp.process_rows(rows, {})
    assert len(records) == 1
    assert records[0]["cod_client"] == 100
    assert len(tobra) == 1
    t = tobra[0]
    assert t["data_dl"] == "2026-06-15"
    assert t["nr_dl"] == "DL1"
    assert t["cod_produs"] == "100"
    assert t["pret_cumparare"] == 3.5
    assert t["pret_vanzare"] == 6.0
    assert t["cantitate"] == 5.0


def test_insert_tobra_rows_is_idempotent():
    erp = _erp()
    conn = sqlite3.connect(":memory:")
    _migration_0013().up(conn)
    rec = {"data_dl": "2026-06-15", "nr_dl": "DL1", "nr_factura": "F1",
           "cod_produs": "100", "sku": "B.TEST TEA", "cantitate": 5.0,
           "pret_cumparare": 3.5, "pret_vanzare": 6.0}
    assert erp.insert_tobra_rows(conn, [rec]) == 1
    assert erp.insert_tobra_rows(conn, [rec]) == 0
    assert conn.execute("SELECT COUNT(*) FROM corr_vanzari_tobra").fetchone()[0] == 1
    assert erp.insert_tobra_rows(conn, []) == 0
