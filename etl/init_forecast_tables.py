"""Create forecast / procurement module tables and seed default lead times."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'torb.db')

conn = sqlite3.connect(DB_PATH)
conn.executescript("""
CREATE TABLE IF NOT EXISTS termene_aprovizionare (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    furnizor        TEXT    NOT NULL,
    zile_livrare    INTEGER NOT NULL DEFAULT 30,
    sezon_craciun   INTEGER NOT NULL DEFAULT 0,
    observatii      TEXT,
    UNIQUE(furnizor)
);

CREATE TABLE IF NOT EXISTS comenzi_furnizori (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    nr_comanda                  TEXT,
    furnizor                    TEXT    NOT NULL,
    data_comanda                DATE    NOT NULL DEFAULT (date('now')),
    status                      TEXT    NOT NULL DEFAULT 'draft',
    data_estimata_livrare       DATE,
    data_confirmare_furnizor    DATE,
    observatii                  TEXT,
    created_at                  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at                  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS comenzi_furnizori_linii (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    comanda_id              INTEGER NOT NULL REFERENCES comenzi_furnizori(id) ON DELETE CASCADE,
    sku                     TEXT    NOT NULL,
    cantitate_sugerat       INTEGER DEFAULT 0,
    cantitate_comandata     INTEGER NOT NULL DEFAULT 0,
    cantitate_confirmata    INTEGER,
    pret_valuta             REAL,
    moneda                  TEXT    DEFAULT 'EUR',
    observatii              TEXT
);
""")

LEAD_TIMES = [
    ('Basilur',    120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai'),
    ('Kings Leaf', 120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai'),
    ('Tipson',     120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai'),
    ('Toras',       45, 0, None),
    ('Delaviuda',   30, 0, None),
    ('Celmar',      30, 0, None),
    ('Leonex',      30, 0, None),
]

for furnizor, zile, sezon, obs in LEAD_TIMES:
    conn.execute(
        "INSERT OR IGNORE INTO termene_aprovizionare (furnizor, zile_livrare, sezon_craciun, observatii)"
        " VALUES (?, ?, ?, ?)",
        (furnizor, zile, sezon, obs)
    )

conn.commit()
conn.close()
print("OK — tabele forecast create + termene sedate.")
