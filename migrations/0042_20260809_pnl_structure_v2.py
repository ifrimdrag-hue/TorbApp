"""Migration 0042 - P&L F1: structure v2 (stable keys + OPEX breakdown).

Phase F1 of docs/plans/2026-07-08-pnl-redesign.md.

Three changes, all on the two reference tables (no balance data is touched):

1. ``pnl_mapping_conturi.pnl_line`` and ``pnl_config.pnl_line`` switch from the
   Romanian display label to a **stable key** (``transport_logistica``), so UI
   text can change without a migration. Existing rows are translated by label.

2. The mapping seed is extended from 35 accounts to the full class 6/7 standard
   Romanian chart at synthetic level (90 rows). Combined with the prefix
   fallback in ``pnl_logic.resolve_cont``, analytic accounts follow their
   synthetic parent, so the unmapped panel only lists genuinely unknown
   accounts.

3. The single coarse OPEX bucket "Servicii terti / logistica / marketing" is
   split into five steerable lines: transport & logistics, marketing, rent &
   utilities, third-party services, consumables. The four alarm rows created by
   the split inherit the old bucket's thresholds.

Net profit is unaffected: remapping moves amounts between lines, every account
keeps its sign, so the computed P&L still reconciles with account 121.
"""

VERSION = 42
NAME = "0042_20260809_pnl_structure_v2"

# (cont, dencont, pnl_line key, semn, categorie)
_MAPPING_SEED = [
    # --- Revenue ---------------------------------------------------------
    ('707',  'VENITURI DIN VANZAREA MARFURILOR',                 'venituri_marfa',     1,  'venituri'),
    ('704',  'VENITURI DIN SERVICII PRESTATE',                   'venituri_servicii',  1,  'venituri'),
    ('705',  'VENITURI DIN STUDII SI CERCETARI',                 'venituri_servicii',  1,  'venituri'),
    ('706',  'VENITURI DIN REDEVENTE, LOCATII DE GESTIUNE SI CHIRII', 'venituri_servicii', 1, 'venituri'),
    ('708',  'VENITURI DIN ACTIVITATI DIVERSE',                  'venituri_servicii',  1,  'venituri'),
    ('709',  'REDUCERI COMERCIALE ACORDATE',                     'reduceri_acordate', -1,  'venituri'),
    # --- Cost of goods ---------------------------------------------------
    ('607',  'CHELTUIELI PRIVIND MARFURILE',                     'cost_marfa',        -1,  'cogs'),
    ('608',  'CHELTUIELI PRIVIND AMBALAJELE',                    'cost_marfa',        -1,  'cogs'),
    ('609',  'REDUCERI COMERCIALE PRIMITE',                      'reduceri_primite',   1,  'cogs'),
    # --- Personnel -------------------------------------------------------
    ('641',  'CHELTUIELI CU SALARIILE PERSONALULUI',             'ch_personal',       -1,  'opex'),
    ('642',  'CHELTUIELI CU AVANTAJELE IN NATURA SI TICHETELE ACORDATE', 'ch_personal', -1, 'opex'),
    ('6421', 'CHELTUIELI CU TICHETELE DE MASA ACORDATE SALARIATILOR', 'ch_personal',   -1,  'opex'),
    ('6422', 'CHELTUIELI CU AVANTAJELE IN NATURA ACORDATE SALARIATILOR', 'ch_personal', -1, 'opex'),
    ('645',  'CHELTUIELI PRIVIND ASIGURARILE SI PROTECTIA SOCIALA', 'ch_personal',     -1,  'opex'),
    ('6451', 'CONTRIBUTIA UNITATII LA ASIGURARILE SOCIALE',      'ch_personal',       -1,  'opex'),
    ('6452', 'CONTRIBUTIA UNITATII PENTRU AJUTORUL DE SOMAJ',    'ch_personal',       -1,  'opex'),
    ('6453', 'CONTRIBUTIA ANGAJATORULUI PENTRU ASIGURARILE SOCIALE DE SANATATE', 'ch_personal', -1, 'opex'),
    ('6456', 'CONTRIBUTIA UNITATII LA SCHEMELE DE PENSII FACULTATIVE', 'ch_personal', -1,  'opex'),
    ('6457', 'CONTRIBUTIA UNITATII LA PRIMELE DE ASIGURARE VOLUNTARA DE SANATATE', 'ch_personal', -1, 'opex'),
    ('6458', 'ALTE CHELTUIELI PRIVIND ASIGURARILE SI PROTECTIA SOCIALA', 'ch_personal', -1, 'opex'),
    ('646',  'CHELTUIELI PRIVIND CONTRIBUTIA ASIGURATORIE PENTRU MUNCA', 'ch_personal', -1, 'opex'),
    # --- Transport & logistics -------------------------------------------
    ('624',  'CHELTUIELI CU TRANSPORTUL DE BUNURI SI PERSONAL',  'transport_logistica', -1, 'opex'),
    ('6022', 'CHELTUIELI PRIVIND COMBUSTIBILII',                 'transport_logistica', -1, 'opex'),
    # --- Marketing --------------------------------------------------------
    ('623',  'CHELTUIELI DE PROTOCOL, RECLAMA SI PUBLICITATE',   'marketing_comercial', -1, 'opex'),
    # --- Rent & utilities -------------------------------------------------
    ('612',  'CHELTUIELI CU REDEVENTELE, LOCATIILE DE GESTIUNE SI CHIRIILE', 'chirii_utilitati', -1, 'opex'),
    ('605',  'CHELTUIELI PRIVIND ENERGIA SI APA',                'chirii_utilitati',  -1,  'opex'),
    # --- Third-party services & admin -------------------------------------
    ('611',  'CHELTUIELI CU INTRETINEREA SI REPARATIILE',        'servicii_terti',    -1,  'opex'),
    ('613',  'CHELTUIELI CU PRIMELE DE ASIGURARE',               'servicii_terti',    -1,  'opex'),
    ('614',  'CHELTUIELI CU STUDIILE SI CERCETARILE',            'servicii_terti',    -1,  'opex'),
    ('621',  'CHELTUIELI CU COLABORATORII',                      'servicii_terti',    -1,  'opex'),
    ('622',  'CHELTUIELI PRIVIND COMISIOANELE SI ONORARIILE',    'servicii_terti',    -1,  'opex'),
    ('625',  'CHELTUIELI CU DEPLASARI, DETASARI SI TRANSFERURI', 'servicii_terti',    -1,  'opex'),
    ('626',  'CHELTUIELI POSTALE SI TAXE DE TELECOMUNICATII',    'servicii_terti',    -1,  'opex'),
    ('627',  'CHELTUIELI CU SERVICIILE BANCARE SI ASIMILATE',    'servicii_terti',    -1,  'opex'),
    ('628',  'ALTE CHELTUIELI CU SERVICIILE EXECUTATE DE TERTI', 'servicii_terti',    -1,  'opex'),
    # --- Consumables ------------------------------------------------------
    ('602',  'CHELTUIELI CU MATERIALELE CONSUMABILE',            'consumabile',       -1,  'opex'),
    ('6021', 'CHELTUIELI PRIVIND MATERIALELE AUXILIARE',         'consumabile',       -1,  'opex'),
    ('6024', 'CHELTUIELI PRIVIND PIESELE DE SCHIMB',             'consumabile',       -1,  'opex'),
    ('6028', 'CHELTUIELI PRIVIND ALTE MATERIALE CONSUMABILE',    'consumabile',       -1,  'opex'),
    ('603',  'CHELTUIELI PRIVIND MATERIALELE DE NATURA OBIECTELOR DE INVENTAR', 'consumabile', -1, 'opex'),
    ('604',  'CHELTUIELI PRIVIND MATERIALELE NESTOCATE',         'consumabile',       -1,  'opex'),
    ('606',  'CHELTUIELI PRIVIND ACTIVELE BIOLOGICE DE NATURA STOCURILOR', 'consumabile', -1, 'opex'),
    # --- Taxes (non-profit) -----------------------------------------------
    ('635',  'CHELTUIELI CU ALTE IMPOZITE, TAXE SI VARSAMINTE ASIMILATE', 'impozite_taxe', -1, 'opex'),
    # --- Other operating expenses -----------------------------------------
    ('654',  'PIERDERI DIN CREANTE SI DEBITORI DIVERSI',         'alte_ch_exploatare', -1, 'opex'),
    ('658',  'ALTE CHELTUIELI DE EXPLOATARE',                    'alte_ch_exploatare', -1, 'opex'),
    ('6581', 'DESPAGUBIRI, AMENZI SI PENALITATI',                'alte_ch_exploatare', -1, 'opex'),
    ('6582', 'DONATII ACORDATE',                                 'alte_ch_exploatare', -1, 'opex'),
    ('6583', 'CHELTUIELI PRIVIND ACTIVELE CEDATE SI ALTE OPERATIUNI DE CAPITAL', 'alte_ch_exploatare', -1, 'opex'),
    ('6584', 'CHELTUIELI CU SUMELE SAU BUNURILE ACORDATE CA SPONSORIZARI', 'alte_ch_exploatare', -1, 'opex'),
    ('6585', 'CHELTUIELI PRIVIND PROTECTIA MEDIULUI INCONJURATOR', 'alte_ch_exploatare', -1, 'opex'),
    ('6586', 'CHELTUIELI REPREZENTAND TRANSFERURI SI CONTRIBUTII DATORATE', 'alte_ch_exploatare', -1, 'opex'),
    ('6587', 'CHELTUIELI PRIVIND CALAMITATILE SI ALTE EVENIMENTE SIMILARE', 'alte_ch_exploatare', -1, 'opex'),
    ('6588', 'ALTE CHELTUIELI DE EXPLOATARE',                    'alte_ch_exploatare', -1, 'opex'),
    # --- Other operating revenue ------------------------------------------
    ('711',  'VENITURI AFERENTE COSTURILOR STOCURILOR DE PRODUSE', 'alte_ven_exploatare', 1, 'opex'),
    ('741',  'VENITURI DIN SUBVENTII DE EXPLOATARE',             'alte_ven_exploatare', 1, 'opex'),
    ('754',  'VENITURI DIN CREANTE REACTIVATE SI DEBITORI DIVERSI', 'alte_ven_exploatare', 1, 'opex'),
    ('758',  'ALTE VENITURI DIN EXPLOATARE',                     'alte_ven_exploatare', 1, 'opex'),
    ('7581', 'VENITURI DIN DESPAGUBIRI, AMENZI SI PENALITATI',   'alte_ven_exploatare', 1, 'opex'),
    ('7582', 'VENITURI DIN DONATII PRIMITE',                     'alte_ven_exploatare', 1, 'opex'),
    ('7583', 'VENITURI DIN VANZAREA ACTIVELOR SI ALTE OPERATIUNI DE CAPITAL', 'alte_ven_exploatare', 1, 'opex'),
    ('7584', 'VENITURI DIN SUBVENTII PENTRU INVESTITII',         'alte_ven_exploatare', 1, 'opex'),
    ('7588', 'ALTE VENITURI DIN EXPLOATARE',                     'alte_ven_exploatare', 1, 'opex'),
    # --- Depreciation & provisions ----------------------------------------
    ('681',  'CHELTUIELI DE EXPLOATARE PRIVIND AMORTIZARILE, PROVIZIOANELE SI AJUSTARILE', 'amortizare_provizioane', -1, 'amortizare'),
    ('6811', 'CHELTUIELI DE EXPLOATARE PRIVIND AMORTIZAREA IMOBILIZARILOR', 'amortizare_provizioane', -1, 'amortizare'),
    ('6812', 'CHELTUIELI DE EXPLOATARE PRIVIND PROVIZIOANELE',   'amortizare_provizioane', -1, 'amortizare'),
    ('6813', 'CHELTUIELI DE EXPLOATARE PRIVIND AJUSTARILE PENTRU DEPRECIEREA IMOBILIZARILOR', 'amortizare_provizioane', -1, 'amortizare'),
    ('6814', 'CHELTUIELI DE EXPLOATARE PRIVIND AJUSTARILE PENTRU DEPRECIEREA ACTIVELOR CIRCULANTE', 'amortizare_provizioane', -1, 'amortizare'),
    ('6817', 'CHELTUIELI DE EXPLOATARE PRIVIND AJUSTARILE PENTRU DEPRECIEREA FONDULUI COMERCIAL', 'amortizare_provizioane', -1, 'amortizare'),
    ('781',  'VENITURI DIN PROVIZIOANE SI AJUSTARI PENTRU DEPRECIERE', 'amortizare_provizioane', 1, 'amortizare'),
    ('7812', 'VENITURI DIN PROVIZIOANE',                         'amortizare_provizioane', 1, 'amortizare'),
    ('7813', 'VENITURI DIN AJUSTARI PENTRU DEPRECIEREA IMOBILIZARILOR', 'amortizare_provizioane', 1, 'amortizare'),
    ('7814', 'VENITURI DIN AJUSTARI PENTRU DEPRECIEREA ACTIVELOR CIRCULANTE', 'amortizare_provizioane', 1, 'amortizare'),
    # --- Financial revenue -------------------------------------------------
    ('761',  'VENITURI DIN IMOBILIZARI FINANCIARE',              'venituri_financiare', 1, 'financiar'),
    ('762',  'VENITURI DIN INVESTITII FINANCIARE PE TERMEN SCURT', 'venituri_financiare', 1, 'financiar'),
    ('763',  'VENITURI DIN CREANTE IMOBILIZATE',                 'venituri_financiare', 1, 'financiar'),
    ('764',  'VENITURI DIN INVESTITII FINANCIARE CEDATE',        'venituri_financiare', 1, 'financiar'),
    ('765',  'VENITURI DIN DIFERENTE DE CURS VALUTAR',           'venituri_financiare', 1, 'financiar'),
    ('766',  'VENITURI DIN DOBANZI',                             'venituri_financiare', 1, 'financiar'),
    ('767',  'VENITURI DIN SCONTURI OBTINUTE',                   'venituri_financiare', 1, 'financiar'),
    ('768',  'ALTE VENITURI FINANCIARE',                         'venituri_financiare', 1, 'financiar'),
    ('786',  'VENITURI FINANCIARE DIN AJUSTARI PENTRU PIERDERE DE VALOARE', 'venituri_financiare', 1, 'financiar'),
    # --- Financial expenses -------------------------------------------------
    ('663',  'PIERDERI DIN CREANTE LEGATE DE PARTICIPATII',      'cheltuieli_financiare', -1, 'financiar'),
    ('664',  'CHELTUIELI PRIVIND INVESTITIILE FINANCIARE CEDATE', 'cheltuieli_financiare', -1, 'financiar'),
    ('665',  'CHELTUIELI DIN DIFERENTE DE CURS VALUTAR',         'cheltuieli_financiare', -1, 'financiar'),
    ('666',  'CHELTUIELI PRIVIND DOBANZILE',                     'cheltuieli_financiare', -1, 'financiar'),
    ('667',  'CHELTUIELI PRIVIND SCONTURILE ACORDATE',           'cheltuieli_financiare', -1, 'financiar'),
    ('668',  'ALTE CHELTUIELI FINANCIARE',                       'cheltuieli_financiare', -1, 'financiar'),
    ('686',  'CHELTUIELI FINANCIARE PRIVIND AMORTIZARILE, PROVIZIOANELE SI AJUSTARILE', 'cheltuieli_financiare', -1, 'financiar'),
    # --- Profit tax ---------------------------------------------------------
    ('691',  'CHELTUIELI CU IMPOZITUL PE PROFIT',                'impozit',           -1,  'impozit'),
    ('698',  'CHELTUIELI CU IMPOZITUL PE VENIT SI CU ALTE IMPOZITE', 'impozit',       -1,  'impozit'),
]

# Old display label -> new stable key. Applied to any pre-existing row (seed or
# owner-added) before the seed is re-applied, so nothing is orphaned.
_OLD_LINE_TO_KEY = {
    'Venituri marfuri':                        'venituri_marfa',
    'Venituri servicii':                       'venituri_servicii',
    'Reduceri comerciale acordate':            'reduceri_acordate',
    'Cost marfa':                              'cost_marfa',
    'Reduceri comerciale primite':             'reduceri_primite',
    'Consumabile / utilitati / combustibil':   'consumabile',
    'Servicii terti / logistica / marketing':  'servicii_terti',
    'Cheltuieli personal':                     'ch_personal',
    'Impozite si taxe':                        'impozite_taxe',
    'Alte cheltuieli exploatare':              'alte_ch_exploatare',
    'Alte venituri exploatare':                'alte_ven_exploatare',
    'Amortizare':                              'amortizare_provizioane',
    'Venituri financiare':                     'venituri_financiare',
    'Cheltuieli financiare':                   'cheltuieli_financiare',
    'Impozit profit':                          'impozit',
}

# (new key, ancestor old key or None, delta_warn, delta_err, prag_warn, prag_err,
#  trend_luni, directie). When the ancestor row still exists its thresholds are
# carried over, so alarm tuning done in /pnl/alarm-config survives. The four
# lines split out of the old OPEX bucket inherit its thresholds.
_CONFIG_SEED = [
    ('ca_neta',             'Cifra de afaceri neta',                  -0.05, -0.10, None, None, 3, 'sus_bine'),
    ('marja_bruta',         'Marja bruta',                            -0.05, -0.10, None, None, 3, 'sus_bine'),
    ('marja_bruta_pct',     'Marja bruta %',                          None,  None,  0.35, 0.30, 3, 'sus_bine'),
    ('ebitda',              'EBITDA',                                 -0.20, -0.40, None, None, 3, 'sus_bine'),
    ('ebitda_pct',          'EBITDA %',                               None,  None,  0.10, 0.05, 3, 'sus_bine'),
    ('profit_net',          'Profit net',                             -0.20, -0.40, None, None, 3, 'sus_bine'),
    ('ch_personal',         'Cheltuieli personal',                    0.15,  0.30,  None, None, 3, 'jos_bine'),
    ('servicii_terti',      'Servicii terti / logistica / marketing', 0.15,  0.25,  None, None, 3, 'jos_bine'),
    ('transport_logistica', 'Servicii terti / logistica / marketing', 0.15,  0.25,  None, None, 3, 'jos_bine'),
    ('marketing_comercial', 'Servicii terti / logistica / marketing', 0.15,  0.25,  None, None, 3, 'jos_bine'),
    ('chirii_utilitati',    'Servicii terti / logistica / marketing', 0.15,  0.25,  None, None, 3, 'jos_bine'),
    ('reduceri_acordate',   'Reduceri comerciale acordate',           0.10,  0.20,  None, None, 3, 'jos_bine'),
]

_CONFIG_COLS = ('alarma_delta_warn', 'alarma_delta_err', 'alarma_prag_warn',
                'alarma_prag_err', 'alarma_trend_luni', 'directie')


def up(conn):
    # 1. Translate every existing mapping row from display label to stable key.
    for old_line, key in _OLD_LINE_TO_KEY.items():
        conn.execute("UPDATE pnl_mapping_conturi SET pnl_line=? WHERE pnl_line=?",
                     (key, old_line))

    # 2. Apply the v2 seed. REPLACE (not IGNORE) so accounts that move between
    #    lines actually move — 6022 consumables -> transport, 612/623/624 out of
    #    the old catch-all bucket, and so on.
    conn.executemany(
        "INSERT OR REPLACE INTO pnl_mapping_conturi(cont,dencont,pnl_line,semn,categorie) "
        "VALUES(?,?,?,?,?)",
        _MAPPING_SEED,
    )

    # 3. Rebuild pnl_config on the new keys, carrying over any tuned thresholds.
    existing = {r[0]: dict(zip(_CONFIG_COLS, r[1:]))
                for r in conn.execute(
                    "SELECT pnl_line, alarma_delta_warn, alarma_delta_err, "
                    "alarma_prag_warn, alarma_prag_err, alarma_trend_luni, directie "
                    "FROM pnl_config")}

    rows = []
    for key, ancestor, dw, de, pw, pe, trend, directie in _CONFIG_SEED:
        prev = existing.get(ancestor) if ancestor else None
        if prev:
            rows.append((key, prev['alarma_delta_warn'], prev['alarma_delta_err'],
                         prev['alarma_prag_warn'], prev['alarma_prag_err'],
                         prev['alarma_trend_luni'], prev['directie']))
        else:
            rows.append((key, dw, de, pw, pe, trend, directie))

    conn.executemany(
        "DELETE FROM pnl_config WHERE pnl_line=?",
        [(old,) for old in {a for _k, a, *_r in _CONFIG_SEED if a}],
    )
    conn.executemany(
        """INSERT OR REPLACE INTO pnl_config
           (pnl_line,alarma_delta_warn,alarma_delta_err,alarma_prag_warn,
            alarma_prag_err,alarma_trend_luni,directie)
           VALUES(?,?,?,?,?,?,?)""",
        rows,
    )
