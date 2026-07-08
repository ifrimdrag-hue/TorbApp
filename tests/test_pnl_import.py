import pytest
import db
import pnl_import


def test_detect_entity():
    assert pnl_import.detect_entity('bal 05 2025 tobra.xls') == 'tobra'
    assert pnl_import.detect_entity('01 2025 torb.xls') == 'torb'
    assert pnl_import.detect_entity('01 2025.xls') == 'torb'  # default


def test_parse_period():
    assert pnl_import.parse_period('01 2025.xls') == (2025, 1)
    assert pnl_import.parse_period('bal 05 2025 tobra.xls') == (2025, 5)
    with pytest.raises(ValueError):
        pnl_import.parse_period('garbage.xls')


def test_persist_rows_and_log():
    conn = db.get_db()
    conn.execute("DELETE FROM pnl_balante_raw")
    conn.execute("DELETE FROM pnl_import_log")
    conn.commit()
    conn.close()
    rows = [{'cont': '707', 'dencont': 'v', 'rulcd': 1000.0}]
    n = pnl_import.persist_rows('src.xls', 'torb', 2025, 1, rows)
    assert n == 1
    got = db.query_one(
        "SELECT rulcd FROM pnl_balante_raw WHERE entitate='torb' AND an=2025 AND luna=1 AND cont='707'")
    assert got['rulcd'] == 1000.0
    log = db.query_one("SELECT status, rows FROM pnl_import_log ORDER BY id DESC LIMIT 1")
    assert log['status'] == 'ok' and log['rows'] == 1


def test_mapping_covers_asset_disposal_accounts():
    # 7583 was missing from the 0033 seed: Tobra 2025 net profit missed the
    # 121 balance by exactly its 16,426.43 RON (migration 0039)
    mapping = {r['cont']: (r['pnl_line'], r['semn']) for r in db.query(
        "SELECT cont, pnl_line, semn FROM pnl_mapping_conturi WHERE cont IN ('7583','6583')")}
    assert mapping['7583'] == ('Alte venituri exploatare', 1)
    assert mapping['6583'] == ('Alte cheltuieli exploatare', -1)
