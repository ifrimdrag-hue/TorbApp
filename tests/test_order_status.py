"""Tests for supplier-order status handling (finding A2 / C2)."""
import importlib.util
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

_MIGRATION = os.path.join(
    os.path.dirname(__file__), '..', 'migrations',
    '0016_20260703_normalize_order_statuses.py',
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_0016", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_normalizes_capitalized_statuses():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE comenzi_furnizori (id INTEGER PRIMARY KEY, status TEXT)")
    conn.executemany(
        "INSERT INTO comenzi_furnizori (status) VALUES (?)",
        [("Emisa",), ("Confirmata",), ("In tranzit",), ("Receptionata",),
         ("in_tranzit",), ("draft",)],
    )
    conn.commit()

    _load_migration().up(conn)

    statuses = sorted(r[0] for r in conn.execute("SELECT status FROM comenzi_furnizori"))
    conn.close()
    # Emisa+Confirmata -> confirmata, In tranzit+in_tranzit -> in_tranzit,
    # Receptionata -> livrata, draft untouched. No capitalized value survives.
    assert statuses == ['confirmata', 'confirmata', 'draft', 'in_tranzit',
                        'in_tranzit', 'livrata']


def test_comanda_update_ignores_empty_status(db_path, client):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        INSERT INTO comenzi_furnizori (nr_comanda, furnizor, status)
        VALUES ('CMD-A2-1', 'TestBrandA2', 'confirmata')
    """)
    cid = conn.execute(
        "SELECT id FROM comenzi_furnizori WHERE nr_comanda='CMD-A2-1'"
    ).fetchone()[0]
    conn.commit()
    conn.close()

    import queries
    # An unmatched UI dropdown posts status='' — this must NOT overwrite the status,
    # but the other fields in the same call must still be applied.
    queries.comanda_update(cid, status='', observatii='nota noua')

    conn = sqlite3.connect(db_path)
    status, obs = conn.execute(
        "SELECT status, observatii FROM comenzi_furnizori WHERE id=?", (cid,)
    ).fetchone()
    conn.close()
    assert status == 'confirmata', "empty status must not overwrite the real status"
    assert obs == 'nota noua', "other fields in the same update must still apply"
