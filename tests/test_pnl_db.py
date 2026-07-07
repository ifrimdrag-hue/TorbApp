import db


def test_pnl_tables_exist():
    names = {r['name'] for r in db.query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pnl_%'")}
    assert {'pnl_balante_raw', 'pnl_mapping_conturi',
            'pnl_config', 'pnl_import_log'} <= names


def test_pnl_seed_counts():
    m = db.query_one("SELECT COUNT(*) AS n FROM pnl_mapping_conturi")['n']
    c = db.query_one("SELECT COUNT(*) AS n FROM pnl_config")['n']
    assert m == 33
    assert c == 9
