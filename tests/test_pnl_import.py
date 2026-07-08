import pytest
import db
import pnl_import


def _clear():
    conn = db.get_db()
    conn.execute("DELETE FROM pnl_balante_raw")
    conn.execute("DELETE FROM pnl_import_log")
    conn.commit()
    conn.close()


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
    _clear()
    rows = [{'cont': '707', 'dencont': 'v', 'rullc': 1000.0, 'rulcd': 1000.0}]
    res = pnl_import.persist_rows('src.xls', 'torb', 2025, 1, rows)
    assert res['rows'] == 1 and res['replaced'] == 0
    got = db.query_one(
        "SELECT rullc FROM pnl_balante_raw WHERE entitate='torb' AND an=2025 AND luna=1 AND cont='707'")
    assert got['rullc'] == 1000.0
    log = db.query_one("SELECT status, rows, replaced FROM pnl_import_log ORDER BY id DESC LIMIT 1")
    assert log['status'] == 'ok' and log['rows'] == 1 and log['replaced'] == 0


def test_full_replace_removes_ghost_rows():
    # First import has 707 + 628; corrected re-import drops 628. It must vanish.
    _clear()
    pnl_import.persist_rows('v1.xls', 'torb', 2025, 1, [
        {'cont': '707', 'rullc': 1000.0, 'rulcd': 1000.0},
        {'cont': '628', 'rulld': 50.0, 'rulcd': 50.0}])
    res = pnl_import.persist_rows('v2.xls', 'torb', 2025, 1, [
        {'cont': '707', 'rullc': 1200.0, 'rulcd': 1200.0}])
    assert res['replaced'] == 2
    conts = {r['cont'] for r in db.query(
        "SELECT cont FROM pnl_balante_raw WHERE entitate='torb' AND an=2025 AND luna=1")}
    assert conts == {'707'}


def test_reimport_is_idempotent():
    _clear()
    rows = [{'cont': '707', 'rullc': 1000.0, 'rulcd': 1000.0},
            {'cont': '607', 'rulld': 400.0, 'rulcd': 400.0}]
    pnl_import.persist_rows('f.xls', 'torb', 2025, 1, rows)
    n1 = db.query_one("SELECT COUNT(*) c FROM pnl_balante_raw")['c']
    pnl_import.persist_rows('f.xls', 'torb', 2025, 1, rows)
    n2 = db.query_one("SELECT COUNT(*) c FROM pnl_balante_raw")['c']
    assert n1 == n2 == 2


def test_validation_echilibru_warns():
    _clear()
    # Debit != credit on the opening balance -> echilibru not ok.
    rows = [{'cont': '707', 'sid': 100.0, 'sic': 0.0, 'rullc': 1000.0, 'rulcd': 1000.0}]
    res = pnl_import.persist_rows('f.xls', 'torb', 2025, 1, rows)
    assert res['validari']['echilibru']['ok'] is False


def test_validation_inlantuire_warns():
    _clear()
    # Jan cumulative rulcd=500. Feb cumulative jumps to 1300 (increment 800) but
    # Feb's own turnover rulld says only 300 -> prior-period correction, warning.
    pnl_import.persist_rows('jan.xls', 'torb', 2025, 1, [
        {'cont': '628', 'rulld': 500.0, 'rulcd': 500.0}])
    res = pnl_import.persist_rows('feb.xls', 'torb', 2025, 2, [
        {'cont': '628', 'rulld': 300.0, 'rulcd': 1300.0}])
    assert res['validari']['inlantuire']['prior_present'] is True
    assert res['validari']['inlantuire']['ok'] is False


def test_validation_inlantuire_clean_when_chained():
    _clear()
    pnl_import.persist_rows('jan.xls', 'torb', 2025, 1, [
        {'cont': '628', 'rulld': 500.0, 'rulcd': 500.0}])
    res = pnl_import.persist_rows('feb.xls', 'torb', 2025, 2, [
        {'cont': '628', 'rulld': 300.0, 'rulcd': 800.0}])
    assert res['validari']['inlantuire']['ok'] is True


def test_validation_reconciliere_121():
    _clear()
    # PN = 707(1000,+1) - 607(400,-1) = 600; 121 sfc-sfd = 600 -> ok.
    res = pnl_import.persist_rows('f.xls', 'torb', 2025, 1, [
        {'cont': '707', 'rullc': 1000.0, 'rulcd': 1000.0},
        {'cont': '607', 'rulld': 400.0, 'rulcd': 400.0},
        {'cont': '121', 'sfc': 600.0, 'sfd': 0.0, 'rulcd': 0.0}])
    assert res['validari']['reconciliere_121']['ok'] is True
    assert res['validari']['reconciliere_121']['diff'] == 0.0


def test_mapping_covers_asset_disposal_accounts():
    # 7583 was missing from the 0033 seed: Tobra 2025 net profit missed the
    # 121 balance by exactly its 16,426.43 RON (migration 0039)
    mapping = {r['cont']: (r['pnl_line'], r['semn']) for r in db.query(
        "SELECT cont, pnl_line, semn FROM pnl_mapping_conturi WHERE cont IN ('7583','6583')")}
    assert mapping['7583'] == ('Alte venituri exploatare', 1)
    assert mapping['6583'] == ('Alte cheltuieli exploatare', -1)
