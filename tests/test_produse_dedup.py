"""Duplicate-produse cleanup: importer no longer creates EAN-as-SKU twins,
and migration 0036 folds existing twins into their numeric-code master."""
import os
import importlib.util
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(relpath, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _catalog_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE produse (
        sku TEXT PRIMARY KEY, descriere TEXT, furnizor TEXT, brand TEXT,
        categorie TEXT, buc_cutie INTEGER, ean TEXT, tva_pct REAL,
        origine TEXT, tara_origine TEXT, activ INTEGER)""")
    conn.execute("""CREATE TABLE tranzactii (
        sku TEXT, furnizor TEXT, val_neta REAL, pret_vanzare REAL)""")
    conn.execute("""CREATE TABLE preturi_vanzare (
        id INTEGER PRIMARY KEY AUTOINCREMENT, an INTEGER, sku TEXT,
        cod_client TEXT, pret_vanzare_ron REAL, activ INTEGER,
        UNIQUE(an, sku, cod_client))""")
    conn.execute("CREATE UNIQUE INDEX idx_pv_std ON preturi_vanzare(an, sku) "
                 "WHERE cod_client IS NULL")
    return conn


# ── Importer: no new EAN-as-SKU twin when the EAN is already catalogued ──────

def test_backfill_skips_catalogued_ean():
    etl = _load("etl/import_preturi.py", "_preturi_etl")
    conn = _catalog_conn()
    # master catalogued under its numeric code, carrying the real EAN
    conn.execute("INSERT INTO produse (sku, descriere, furnizor, ean, activ) "
                 "VALUES ('302','Articol cod 302','Solvex','3800708381725',1)")
    # a Solvex sale using the long concatenated SKU that embeds that EAN
    conn.execute("INSERT INTO tranzactii (sku, furnizor, val_neta, pret_vanzare) VALUES "
                 "('302 MISS MAGIC ARGINT POLAR 3800708381725','Solvex',100,12.5)")
    # a genuinely new product (EAN not catalogued) — positive control
    conn.execute("INSERT INTO tranzactii (sku, furnizor, val_neta, pret_vanzare) VALUES "
                 "('NEW THING 4000000000009','Solvex',50,9.0)")

    etl.import_unmatched_from_tranzactii(conn)

    skus = {r[0] for r in conn.execute("SELECT sku FROM produse")}
    assert '3800708381725' not in skus       # duplicate NOT created
    assert '302' in skus
    assert '4000000000009' in skus           # real new product still catalogued
    # no phantom price under the EAN
    assert conn.execute(
        "SELECT COUNT(*) FROM preturi_vanzare WHERE sku='3800708381725'").fetchone()[0] == 0


# ── Migration 0036: fold existing twins into the master ──────────────────────

def test_migration_0036_consolidates_twins():
    mig = _load("migrations/0036_20260707_produse_dedup_ean_twins.py", "_mig36")
    conn = _catalog_conn()
    # pair A: master already has a list price; twin has a conflicting avg price
    conn.execute("INSERT INTO produse (sku, descriere, furnizor, ean, buc_cutie, activ) "
                 "VALUES ('302','Articol cod 302','Solvex','3800708381725',20,1)")
    conn.execute("INSERT INTO produse (sku, descriere, furnizor, ean, activ) "
                 "VALUES ('3800708381725','302 MISS MAGIC ARGINT POLAR','Solvex',NULL,1)")
    conn.execute("INSERT INTO preturi_vanzare (an, sku, cod_client, pret_vanzare_ron, activ) "
                 "VALUES (2026,'302',NULL,10.0,1)")
    conn.execute("INSERT INTO preturi_vanzare (an, sku, cod_client, pret_vanzare_ron, activ) "
                 "VALUES (2026,'3800708381725',NULL,9.5,1)")
    # pair B: price lives ONLY on the twin → must survive on the master
    conn.execute("INSERT INTO produse (sku, descriere, furnizor, ean, activ) "
                 "VALUES ('303','Articol cod 303','Solvex','3800708381732',1)")
    conn.execute("INSERT INTO produse (sku, descriere, furnizor, ean, activ) "
                 "VALUES ('3800708381732','303 MISS MAGIC NISIP','Solvex',NULL,1)")
    conn.execute("INSERT INTO preturi_vanzare (an, sku, cod_client, pret_vanzare_ron, activ) "
                 "VALUES (2026,'3800708381732',NULL,7.0,1)")

    mig.up(conn)

    skus = {r[0] for r in conn.execute("SELECT sku FROM produse")}
    assert skus == {'302', '303'}                     # both twins removed
    # master descriere enriched from the twin's real name
    assert conn.execute("SELECT descriere FROM produse WHERE sku='302'"
                        ).fetchone()[0] == '302 MISS MAGIC ARGINT POLAR'
    # master's own list price wins over the twin's avg price
    assert conn.execute("SELECT pret_vanzare_ron FROM preturi_vanzare "
                        "WHERE sku='302' AND cod_client IS NULL").fetchone()[0] == 10.0
    # twin-only price preserved onto the master
    assert conn.execute("SELECT pret_vanzare_ron FROM preturi_vanzare "
                        "WHERE sku='303' AND cod_client IS NULL").fetchone()[0] == 7.0
    # no orphan prices left on the deleted twins
    assert conn.execute("SELECT COUNT(*) FROM preturi_vanzare "
                        "WHERE sku IN ('3800708381725','3800708381732')").fetchone()[0] == 0
