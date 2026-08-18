"""Fuziuni de clienți: Profi Rom Food SRL → Mega Image SRL.

Acoperă cele două puncte de intrare (rescrierea la import și trecerea peste
bază) plus migrarea 0043, ca reatribuirea să reziste la actualizarea zilnică.
"""
import importlib.util
import os
import sqlite3

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cm():
    return _load(os.path.join(ROOT, "etl", "client_merges.py"), "_client_merges")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript("""
        CREATE TABLE tranzactii (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client TEXT, cod_client TEXT, cui_client TEXT, tip_client TEXT,
            oras_client TEXT, judet_client TEXT, agent TEXT, val_neta REAL,
            nr_dl TEXT, cod_produs TEXT, nr_factura TEXT, pret_vanzare REAL,
            UNIQUE(nr_dl, cod_produs, nr_factura, pret_vanzare)
        );
        CREATE TABLE solduri_neincasate (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numecli TEXT, codcli TEXT, cfcli TEXT, sumdeincas REAL
        );
        CREATE TABLE clienti_pricing (cod_client TEXT PRIMARY KEY, nume TEXT);
    """)
    yield c
    c.close()


def _tx(conn, cod_client, client, nr_dl, val=100.0, **extra):
    cols = {"client": client, "cod_client": cod_client, "nr_dl": nr_dl,
            "cod_produs": "P1", "nr_factura": "F1", "pret_vanzare": 10.0,
            "val_neta": val, **extra}
    conn.execute(
        f"INSERT INTO tranzactii ({', '.join(cols)}) "
        f"VALUES ({', '.join('?' * len(cols))})",
        list(cols.values()),
    )


# ── apply_record: rescrierea la momentul importului ─────────────────────────

def test_apply_record_rewrites_profi_identity(cm):
    record = {"cod_client": "973", "client": "PROFI ROM FOOD SRL",
              "cui_client": "RO11607939", "tip_client": "SUPERMARKET",
              "oras_client": "Timisoara", "agent": "Oana Filip"}
    assert cm.apply_record(record) is True
    assert record["cod_client"] == "4909"
    assert record["client"] == "MEGA IMAGE SRL"
    assert record["cui_client"] == "RO6719278"
    # locația fizică și agentul rămân neatinse
    assert record["oras_client"] == "Timisoara"
    assert record["agent"] == "Oana Filip"


def test_apply_record_accepts_numeric_cod_client(cm):
    """Importul ERP scrie cod_client ca int; raportul de solduri, ca '973.0'."""
    for cod in (973, 973.0, "973.0", " 973 "):
        record = {"cod_client": cod, "client": "PROFI ROM FOOD SRL",
                  "cui_client": None, "tip_client": None}
        assert cm.apply_record(record) is True, cod
        assert record["cod_client"] == "4909"


def test_apply_record_leaves_other_clients_alone(cm):
    record = {"cod_client": "4909", "client": "MEGA IMAGE SRL",
              "cui_client": "RO6719278", "tip_client": "SUPERMARKET"}
    assert cm.apply_record(record) is False
    record = {"cod_client": None, "client": None,
              "cui_client": None, "tip_client": None}
    assert cm.apply_record(record) is False


# ── run(): trecerea peste bază ──────────────────────────────────────────────

def test_run_moves_history_and_is_idempotent(cm, conn):
    _tx(conn, "973", "PROFI ROM FOOD SRL", "DL1", 100.0, cui_client="RO11607939")
    _tx(conn, 973, "PROFI ROM FOOD SRL", "DL2", 50.0)
    _tx(conn, "4909", "MEGA IMAGE SRL", "DL3", 25.0)
    _tx(conn, "1", "KAUFLAND ROMANIA", "DL4", 10.0)
    conn.commit()

    cm.run(conn, verbose=False)

    assert conn.execute(
        "SELECT COUNT(*) FROM tranzactii WHERE cod_client = '973'"
    ).fetchone()[0] == 0
    n, val = conn.execute(
        "SELECT COUNT(*), SUM(val_neta) FROM tranzactii WHERE cod_client = '4909'"
    ).fetchone()
    assert (n, val) == (3, 175.0)
    assert {r[0] for r in conn.execute(
        "SELECT DISTINCT client, cui_client FROM tranzactii WHERE cod_client = '4909'"
    )} == {"MEGA IMAGE SRL"}
    # clienții străini de fuziune nu se ating
    assert conn.execute(
        "SELECT client FROM tranzactii WHERE cod_client = '1'"
    ).fetchone()[0] == "KAUFLAND ROMANIA"

    # a doua rulare nu mai are ce muta
    assert cm.run(conn, verbose=False) == {}


def test_run_moves_solduri_with_float_client_code(cm, conn):
    conn.execute(
        "INSERT INTO solduri_neincasate (numecli, codcli, cfcli, sumdeincas)"
        " VALUES ('PROFI ROM FOOD SRL', '973.0', 'RO11607939', 4200.0)"
    )
    conn.commit()

    cm.run(conn, verbose=False)

    row = conn.execute(
        "SELECT numecli, codcli, cfcli, sumdeincas FROM solduri_neincasate"
    ).fetchone()
    assert row == ("MEGA IMAGE SRL", "4909", "RO6719278", 4200.0)


def test_run_drops_config_row_when_target_already_has_one(cm, conn):
    """Cheie unică pe cod_client: valoarea clientului supraviețuitor câștigă."""
    conn.executemany(
        "INSERT INTO clienti_pricing (cod_client, nume) VALUES (?, ?)",
        [("973", "profi"), ("4909", "mega")],
    )
    conn.commit()

    report = cm.run(conn, verbose=False)

    assert report[("973", "clienti_pricing")] == (0, 1)
    assert conn.execute(
        "SELECT cod_client, nume FROM clienti_pricing"
    ).fetchall() == [("4909", "mega")]


def test_run_skips_tables_absent_from_the_schema(cm):
    """Schemele mai vechi nu au toate tabelele — trecerea nu trebuie să crape."""
    bare = sqlite3.connect(":memory:")
    bare.execute("CREATE TABLE tranzactii (cod_client TEXT, client TEXT)")
    assert cm.run(bare, verbose=False) == {}
    bare.close()


# ── migrarea 0043: aceeași reatribuire pe baza existentă ────────────────────

def test_migration_0043_matches_the_etl_mapping(cm, conn):
    mig = _load(
        os.path.join(ROOT, "migrations", "0043_20260817_client_merge_profi_mega.py"),
        "_migration_0043",
    )
    assert mig.VERSION == 43
    assert mig.MEGA == {k: v for k, v in cm.CLIENT_MERGES["973"].items() if k != "sursa"}
    assert [t[0] for t in mig.TABLES] == [t[0] for t in cm.CLIENT_TABLES]

    _tx(conn, "973", "PROFI ROM FOOD SRL", "DL1", 100.0)
    conn.commit()
    mig.up(conn)
    mig.up(conn)  # idempotentă

    assert conn.execute(
        "SELECT client, cod_client FROM tranzactii"
    ).fetchall() == [("MEGA IMAGE SRL", "4909")]
