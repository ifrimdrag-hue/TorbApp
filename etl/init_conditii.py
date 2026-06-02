import sqlite3

conn = sqlite3.connect('data/torb.db')
conn.execute('''
CREATE TABLE IF NOT EXISTS conditii_comerciale (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    an            INTEGER NOT NULL,
    cod_client    TEXT,
    furnizor      TEXT,
    tip_valoare   TEXT NOT NULL CHECK(tip_valoare IN ("pct","suma_fixa")),
    periodicitate TEXT NOT NULL CHECK(periodicitate IN ("lunar","anual","unic")),
    valoare       REAL NOT NULL,
    descriere     TEXT,
    data_creare   TEXT
)''')
conn.execute('''
CREATE TABLE IF NOT EXISTS termene_plata (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    an          INTEGER NOT NULL,
    cod_client  TEXT NOT NULL,
    zile_termen INTEGER NOT NULL,
    observatii  TEXT,
    data_creare TEXT
)''')
conn.execute('CREATE INDEX IF NOT EXISTS idx_cc_an_client ON conditii_comerciale(an, cod_client)')
conn.execute('CREATE INDEX IF NOT EXISTS idx_tp_an_client ON termene_plata(an, cod_client)')
conn.commit()
conn.close()
print('OK')
