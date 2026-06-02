"""Initialize pricing module tables."""
import sqlite3

conn = sqlite3.connect('data/torb.db')

conn.executescript("""
CREATE TABLE IF NOT EXISTS produse (
    sku           TEXT PRIMARY KEY,
    descriere     TEXT,
    furnizor      TEXT,
    brand         TEXT,
    categorie     TEXT,
    gramaj        REAL,
    buc_cutie     INTEGER,
    ean           TEXT,
    tva_pct       REAL DEFAULT 0.09,
    hs_code       TEXT,
    taxa_vamala_mfn_pct  REAL DEFAULT 0,
    taxa_vamala_pct      REAL DEFAULT 0,
    origine       TEXT DEFAULT 'import_extraeu',
    tara_origine  TEXT,
    activ         INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rate_schimb (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    an        INTEGER NOT NULL,
    moneda    TEXT NOT NULL,
    curs_ron  REAL NOT NULL,
    UNIQUE(an, moneda)
);

CREATE TABLE IF NOT EXISTS costuri_landing (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    an                    INTEGER NOT NULL,
    sku                   TEXT NOT NULL,
    moneda                TEXT NOT NULL DEFAULT 'USD',
    pret_achizitie_valuta REAL,
    curs_ron              REAL,
    pret_achizitie_ron    REAL,
    transport_pct         REAL DEFAULT 10.0,
    taxa_vamala_pct       REAL DEFAULT 0.0,
    alte_costuri_ron      REAL DEFAULT 0.0,
    landing_cost_ron      REAL,
    UNIQUE(an, sku)
);

CREATE TABLE IF NOT EXISTS preturi_vanzare (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    an              INTEGER NOT NULL,
    sku             TEXT NOT NULL,
    cod_client      TEXT,
    pret_vanzare_ron REAL NOT NULL,
    activ           INTEGER DEFAULT 1,
    UNIQUE(an, sku, cod_client)
);

CREATE INDEX IF NOT EXISTS idx_pv_sku ON preturi_vanzare(sku);
CREATE INDEX IF NOT EXISTS idx_cl_sku ON costuri_landing(sku);
""")

conn.commit()
conn.close()
print('Tabele preturi create OK')
