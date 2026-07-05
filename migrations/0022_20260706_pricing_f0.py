"""Migration 0022 - pricing module F0 foundations.

New tables for the pricing/offers module (docs/plans/2026-07-05-modul-pricing-ofertare.md):
  - produse_logistica    1:1 logistics master per SKU (dims, weights, CBM, units/case)
  - produse_media        product photos (local file and/or source URL)
  - coduri_client_articol  per-client internal article codes (Metro, Kaufland, ...)
  - pricing_config       margin thresholds etc.; gama='' = global default (owner
                         rule: nothing hardcoded - thresholds are data, not code)
  - clienti_pricing      per-client pricing settings (simulated shelf margin,
                         listing export template key)
Also widens conditii_comerciale with optional categorie/sku scope columns
(owner decision #4: conditions differ per category and per product).
"""
import sqlite3

VERSION = 22
NAME = "0022_20260706_pricing_f0"


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS produse_logistica (
            sku            TEXT PRIMARY KEY,
            unit_l_mm      REAL,
            unit_w_mm      REAL,
            unit_h_mm      REAL,
            unit_net_kg    REAL,
            unit_gross_kg  REAL,
            bax_l_mm       REAL,
            bax_w_mm       REAL,
            bax_h_mm       REAL,
            bax_gross_kg   REAL,
            bax_cbm        REAL,
            buc_bax        INTEGER,
            bax_palet      INTEGER,
            valabilitate_luni INTEGER,
            moq            INTEGER,
            sursa          TEXT,
            updated_at     DATETIME DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS produse_media (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            sku        TEXT NOT NULL,
            path       TEXT,
            url_sursa  TEXT,
            principala INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT (datetime('now','localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_media_sku ON produse_media(sku);

        CREATE TABLE IF NOT EXISTS coduri_client_articol (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sku         TEXT NOT NULL,
            cod_client  TEXT NOT NULL,
            cod_intern  TEXT,
            cod_intern2 TEXT,
            sursa       TEXT,
            UNIQUE(sku, cod_client)
        );
        CREATE INDEX IF NOT EXISTS idx_cca_client ON coduri_client_articol(cod_client);

        CREATE TABLE IF NOT EXISTS pricing_config (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            gama    TEXT NOT NULL DEFAULT '',
            cheie   TEXT NOT NULL,
            valoare TEXT NOT NULL,
            UNIQUE(gama, cheie)
        );

        CREATE TABLE IF NOT EXISTS clienti_pricing (
            cod_client       TEXT PRIMARY KEY,
            nume_client      TEXT,
            marja_raft_pct   REAL,
            template_listare TEXT,
            activ            INTEGER DEFAULT 1
        );
    """)

    conn.execute("INSERT OR IGNORE INTO pricing_config(gama, cheie, valoare) "
                 "VALUES ('', 'marja_minima_pct', '30')")
    conn.execute("INSERT OR IGNORE INTO pricing_config(gama, cheie, valoare) "
                 "VALUES ('', 'marja_aprobare_pct', '25')")

    for col in ("categorie TEXT", "sku TEXT"):
        try:
            conn.execute(f"ALTER TABLE conditii_comerciale ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass  # column already present (re-run on a patched DB)
