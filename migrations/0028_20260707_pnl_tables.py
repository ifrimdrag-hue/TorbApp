"""Migration 0028 - P&L module tables (relocated from standalone pnl_app).

Four pnl_-prefixed tables. pnl_mapping_conturi (account -> P&L line) and
pnl_config (per-line alarm thresholds) are reference tables, seeded here.
pnl_balante_raw and pnl_import_log start empty on every environment; real
balance data arrives via the module's Excel upload.
"""

VERSION = 28
NAME = "0028_20260707_pnl_tables"

_MAPPING_SEED = [
    ('707',  'VENITURI DIN VANZARI MARFURI',                   'Venituri marfuri',                        1,  'venituri'),
    ('704',  'VENITURI DIN LUCR.EXEC.,SERV.PRESTATE',          'Venituri servicii',                       1,  'venituri'),
    ('709',  'REDUCERI COMERCIALE ACORDATE',                    'Reduceri comerciale acordate',           -1,  'venituri'),
    ('607',  'CHELT PRIVIND MARFURILE',                         'Cost marfa',                             -1,  'cogs'),
    ('609',  'REDUCERI COMERCIALE PRIMITE',                     'Reduceri comerciale primite',             1,  'cogs'),
    ('6022', 'CHELT COMBUSTIBIL',                               'Consumabile / utilitati / combustibil', -1,  'opex'),
    ('6028', 'CHELT. CU MATERIALE CONSUMABILE',                 'Consumabile / utilitati / combustibil', -1,  'opex'),
    ('603',  'CHELT PRIVIND MATERIALELE DE NATURA OB.INVENTAR', 'Consumabile / utilitati / combustibil', -1,  'opex'),
    ('605',  'CHELT. PRIVIND ENERGIA SI APA',                   'Consumabile / utilitati / combustibil', -1,  'opex'),
    ('611',  'CHELT. CU INTRETINEREA SI REPARATIILE',           'Servicii terti / logistica / marketing',-1,  'opex'),
    ('612',  'CHELT. CU REDEVENTELE LOC.GEST, CHIRII',          'Servicii terti / logistica / marketing',-1,  'opex'),
    ('613',  'CHELTUIELI CU PRIMELE DE ASIGURARE',              'Servicii terti / logistica / marketing',-1,  'opex'),
    ('622',  'CHELT. PRIVIND COMISIOANELE SI ONORARIILE',       'Servicii terti / logistica / marketing',-1,  'opex'),
    ('623',  'CHELT PROTOCOL, RECLAMA SI PUBLICITATE',          'Servicii terti / logistica / marketing',-1,  'opex'),
    ('624',  'CHELTUIELI CU TRANSPORTUL DE BUNURI SI PERSONAL', 'Servicii terti / logistica / marketing',-1,  'opex'),
    ('625',  'CHELT. CU DEPLASARI,DETASARI,TRANSFERURI',        'Servicii terti / logistica / marketing',-1,  'opex'),
    ('626',  'CHELT.POSTALE SI TAXE DE COMUNICATII',            'Servicii terti / logistica / marketing',-1,  'opex'),
    ('627',  'CHELT. CU SERVICII BANCARE SI ASIMILATE',         'Servicii terti / logistica / marketing',-1,  'opex'),
    ('628',  'ALTE CHELT. CU SERVICII EXECUT. DE TERTI',        'Servicii terti / logistica / marketing',-1,  'opex'),
    ('641',  'CHELT. SALARIILE  PERSONALULUI',                  'Cheltuieli personal',                   -1,  'opex'),
    ('6458', 'ALTE CHELTUIELI PRIVIND ASIGURARILE',             'Cheltuieli personal',                   -1,  'opex'),
    ('635',  'CHELT. CU ALTE IMPOZITE,TAXE,VARSAM.ASIM',        'Impozite si taxe',                      -1,  'opex'),
    ('6581', 'DEZPAGUBIRI, AMENZI SI PENALITATI',               'Alte cheltuieli exploatare',            -1,  'opex'),
    ('6584', 'CHELTUIELI CU SPONSORIZARI',                      'Alte cheltuieli exploatare',            -1,  'opex'),
    ('6588', 'ALTE CHELTUIELI DIN EXPLOATARE',                  'Alte cheltuieli exploatare',            -1,  'opex'),
    ('758',  'ALTE VENITURI DIN EXPLOATARE',                    'Alte venituri exploatare',               1,  'opex'),
    ('7588', 'ALTE VENITURI DIN EXPLOATARE',                    'Alte venituri exploatare',               1,  'opex'),
    ('6811', 'CHELT DE EXPLOATARE PRIVIND AMORTIZARILE',        'Amortizare',                            -1,  'amortizare'),
    ('765',  'VENITURI DIN DIFERENTE DE CURS VALUTAR',          'Venituri financiare',                    1,  'financiar'),
    ('766',  'VENITURI DIN DOBANZI',                            'Venituri financiare',                    1,  'financiar'),
    ('665',  'CHELT DIN DIFERENTE DE CURS VALUTAR',             'Cheltuieli financiare',                 -1,  'financiar'),
    ('666',  'CHELT.PRIVIND DOBANZILE',                         'Cheltuieli financiare',                 -1,  'financiar'),
    ('691',  'CHELT. CU IMPOZITUL PE PROFIT',                   'Impozit profit',                        -1,  'impozit'),
]

_CONFIG_SEED = [
    ('Cifra de afaceri neta',               -0.05, -0.10, None, None, 3, 'sus_bine'),
    ('Marja bruta',                         -0.05, -0.10, None, None, 3, 'sus_bine'),
    ('Marja bruta %',                       None,  None,  0.35, 0.30, 3, 'sus_bine'),
    ('EBITDA',                              -0.20, -0.40, None, None, 3, 'sus_bine'),
    ('EBITDA %',                            None,  None,  0.10, 0.05, 3, 'sus_bine'),
    ('Profit net',                          -0.20, -0.40, None, None, 3, 'sus_bine'),
    ('Cheltuieli personal',                  0.15,  0.30, None, None, 3, 'jos_bine'),
    ('Servicii terti / logistica / marketing', 0.15, 0.25, None, None, 3, 'jos_bine'),
    ('Reduceri comerciale acordate',         0.10,  0.20, None, None, 3, 'jos_bine'),
]


def up(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pnl_balante_raw (
            id          INTEGER PRIMARY KEY,
            source_file TEXT,
            entitate    TEXT,
            an          INTEGER,
            luna        INTEGER,
            cont        TEXT,
            dencont     TEXT,
            sid  REAL, sic  REAL, sfd  REAL, sfc  REAL,
            rulld REAL, rullc REAL, rulcd REAL, rulcc REAL,
            UNIQUE(entitate, an, luna, cont) ON CONFLICT REPLACE
        );
        CREATE TABLE IF NOT EXISTS pnl_mapping_conturi (
            cont      TEXT PRIMARY KEY,
            dencont   TEXT,
            pnl_line  TEXT,
            semn      INTEGER,
            categorie TEXT
        );
        CREATE TABLE IF NOT EXISTS pnl_config (
            pnl_line          TEXT PRIMARY KEY,
            alarma_delta_warn REAL,
            alarma_delta_err  REAL,
            alarma_prag_warn  REAL,
            alarma_prag_err   REAL,
            alarma_trend_luni INTEGER DEFAULT 3,
            directie          TEXT DEFAULT 'sus_bine'
        );
        CREATE TABLE IF NOT EXISTS pnl_import_log (
            id          INTEGER PRIMARY KEY,
            timestamp   TEXT,
            source_file TEXT,
            entitate    TEXT,
            an          INTEGER,
            luna        INTEGER,
            rows        INTEGER,
            status      TEXT
        );
    """)
    conn.executemany(
        "INSERT OR IGNORE INTO pnl_mapping_conturi(cont,dencont,pnl_line,semn,categorie) VALUES(?,?,?,?,?)",
        _MAPPING_SEED,
    )
    conn.executemany(
        """INSERT OR IGNORE INTO pnl_config
           (pnl_line,alarma_delta_warn,alarma_delta_err,alarma_prag_warn,alarma_prag_err,alarma_trend_luni,directie)
           VALUES(?,?,?,?,?,?,?)""",
        _CONFIG_SEED,
    )
