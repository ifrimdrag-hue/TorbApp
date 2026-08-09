import db


def test_pnl_tables_exist():
    names = {r['name'] for r in db.query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'pnl_%'")}
    assert {'pnl_balante_raw', 'pnl_mapping_conturi',
            'pnl_config', 'pnl_import_log'} <= names


def test_pnl_seed_counts():
    m = db.query_one("SELECT COUNT(*) AS n FROM pnl_mapping_conturi")['n']
    c = db.query_one("SELECT COUNT(*) AS n FROM pnl_config")['n']
    assert m == 90  # full class 6/7 chart reseeded by 0042
    assert c == 12  # 9 alarm rows + 3 from the OPEX split (0042)


def test_pnl_reference_rows_use_structure_keys():
    """Every mapping/alarm row must point at a key the P&L structure knows —
    a stale label would silently drop that account from the statement."""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'app'))
    import pnl_logic
    keys = {key for _t, _lbl, key in pnl_logic.PNL_STRUCTURE}
    mapped = {r['pnl_line'] for r in db.query(
        "SELECT DISTINCT pnl_line FROM pnl_mapping_conturi")}
    configured = {r['pnl_line'] for r in db.query(
        "SELECT DISTINCT pnl_line FROM pnl_config")}
    assert mapped <= keys, f"unknown mapping lines: {mapped - keys}"
    assert configured <= keys, f"unknown alarm lines: {configured - keys}"


def test_opex_split_alarms_inherit_old_thresholds():
    rows = {r['pnl_line']: r for r in db.query(
        "SELECT * FROM pnl_config WHERE pnl_line IN "
        "('transport_logistica','marketing_comercial','chirii_utilitati','servicii_terti')")}
    assert len(rows) == 4
    for r in rows.values():
        assert r['alarma_delta_warn'] == 0.15
        assert r['alarma_delta_err'] == 0.25
        assert r['directie'] == 'jos_bine'
