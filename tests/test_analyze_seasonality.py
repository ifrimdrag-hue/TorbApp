"""Tests for etl/analyze_seasonality.py.

Covers the two places the report can be silently wrong: the channel mapping
(a mis-mapped tip_client hides revenue in the wrong segment) and the P&L
turnover column (rulld = the month's own turnover, rulcd = cumulative YTD --
using the latter inflates fixed costs, and with them the breakeven).
"""
import importlib.util
import os
import sqlite3
import tempfile

import pytest

# Loaded by path, not via sys.path: etl/ holds a backup_db.py shim that shadows
# app/backup_db.py, so putting etl/ on sys.path breaks test_backup_db.
_SPEC = importlib.util.spec_from_file_location(
    'analyze_seasonality',
    os.path.join(os.path.dirname(__file__), '..', 'etl', 'analyze_seasonality.py'))
az = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(az)


# ── channel mapping ──────────────────────────────────────────────────────────

def test_grup_canal_maps_pharma_spellings():
    # The ERP ships both the typo and the correct spelling.
    assert az.grup_canal('DISTRUBUITOR PHARMA') == 'PHARMA'
    assert az.grup_canal('DISTRIBUITOR PHARMA') == 'PHARMA'
    assert az.grup_canal('FARMACIE') == 'PHARMA'

def test_grup_canal_case_and_whitespace_insensitive():
    assert az.grup_canal('  hypermarket ') == 'IKA'

def test_grup_canal_null_is_altele():
    assert az.grup_canal(None) == 'ALTELE'

def test_grup_canal_unknown_is_flagged_not_swallowed():
    # An unmapped type must never land in TT by default -- it has to show up.
    assert az.grup_canal('CANAL NOU SRL') == 'NECLASIFICAT'

def test_tt_and_ika_stay_separate():
    assert az.grup_canal('MAGAZIN') == 'TT'
    assert az.grup_canal('SUPERMARKET') == 'IKA'


# ── account resolution (mirrors app/pnl_logic.resolve_cont) ──────────────────

def test_resolve_cont_exact_match_wins():
    assert az.resolve_cont('641', {'641': 'personal', '64': 'x'}) == 'personal'

def test_resolve_cont_analytic_falls_back_to_parent():
    assert az.resolve_cont('6221', {'622': 'servicii'}) == 'servicii'

def test_resolve_cont_does_not_match_below_three_chars():
    # '62' is too short to be a synthetic parent; nothing should match.
    assert az.resolve_cont('6221', {'62': 'servicii'}) is None

def test_resolve_cont_unmapped_returns_none():
    assert az.resolve_cont('999', {'641': 'personal'}) is None


# ── report generation on a real (tiny) database ──────────────────────────────

@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE tranzactii (
            an INT, luna INT, furnizor TEXT, val_neta REAL, val_bruta REAL,
            marja_bruta REAL, discount_pct REAL, discount_val REAL,
            client TEXT, cod_client TEXT, tip_client TEXT, agent TEXT);
        CREATE TABLE pnl_balante_raw (
            entitate TEXT, an INT, luna INT, cont TEXT, dencont TEXT,
            sfd REAL, sfc REAL, rulld REAL, rullc REAL, rulcd REAL, rulcc REAL);
        CREATE TABLE pnl_mapping_conturi (
            cont TEXT PRIMARY KEY, dencont TEXT, pnl_line TEXT,
            semn INT, categorie TEXT);
    """)
    # 2025: 100k every month except December, which triples. Two channels.
    for luna in range(1, 13):
        val = 300000.0 if luna == 12 else 100000.0
        for tip, agent in (('MAGAZIN', 'AG1'), ('FARMACIE', 'AG2')):
            conn.execute(
                "INSERT INTO tranzactii (an, luna, furnizor, val_neta, val_bruta,"
                " marja_bruta, discount_pct, discount_val, client, cod_client,"
                " tip_client, agent) VALUES (2025,?,?,?,?,?,0,0,?,?,?,?)",
                (luna, 'Basilur', val, val, val * 0.3, 'C' + tip, tip, tip, agent))
    # Six months of OPEX: 10k/month own turnover, cumulative climbing to 60k.
    for luna in range(1, 7):
        conn.execute(
            "INSERT INTO pnl_balante_raw (entitate, an, luna, cont, dencont,"
            " sfd, sfc, rulld, rullc, rulcd, rulcc)"
            " VALUES ('torb',2026,?,'6411','Salarii',0,0,10000,0,?,0)",
            (luna, 10000 * luna))
    conn.execute("INSERT INTO pnl_mapping_conturi VALUES"
                 " ('641','Salarii','Cheltuieli personal',-1,'opex')")
    conn.commit()
    conn.close()
    yield path
    os.unlink(path)


def _run(db_path, sectiuni):
    az.OUT.clear()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for cheie in sectiuni:
        fn = az.SECTIUNI[cheie]
        fn(conn, 2026) if cheie in ('q5', 'q6') else fn(conn)
    conn.close()
    return "\n".join(az.OUT)


def test_q1_splits_tt_and_pharma_and_flags_the_q4_peak(db):
    out = _run(db, ['q1'])
    assert '| TT |' in out and '| PHARMA |' in out
    # Per channel: 300k in each of Q1..Q3, 500k in Q4 (December triples),
    # so 300/1400 = 21.4% and 500/1400 = 35.7%.
    assert '21.4%' in out and '35.7%' in out
    assert 'puternic sezonier' in out


def test_q2_ranks_the_weakest_months_ahead_of_december(db):
    out = _run(db, ['q2'])
    # December triples, so it must not be among the three weakest months.
    slabe = out.split('**Cele mai slabe 3 luni:')[1].split('**')[0]
    assert 'dec' not in slabe


def test_q5_uses_the_months_own_turnover_not_the_cumulative_one(db):
    out = _run(db, ['q5'])
    # Six months x 10,000 own turnover = 60,000 cumulated, 10,000 average.
    # Summing rulcd instead would give 210,000 / 35,000 and a 3.5x breakeven.
    linie = [ln for ln in out.split("\n") if 'TOTAL OPEX' in ln][0]
    assert '60.000' in linie and '10.000' in linie


def test_q5_resolves_analytic_accounts_onto_the_mapped_parent(db):
    # The balance carries 6411; only 641 is mapped.
    assert 'Cheltuieli personal' in _run(db, ['q5'])


def test_q7_reports_missing_data_instead_of_estimating(db):
    out = _run(db, ['q7'])
    assert 'Nu există date pentru un răspuns cantitativ' in out


def test_missing_tables_are_reported_not_crashed(db):
    # No solduri_neincasate / conditii_comerciale in this fixture.
    out = _run(db, ['q4', 'q8'])
    assert 'Date indisponibile' in out
