"""Migration 0039 — map asset-disposal accounts in the P&L.

Tobra's 2025 balances carry account 7583 (VENITURI DIN CEDARI DE ACTIVE),
absent from the 0033 mapping seed, so its 16,426.43 RON never reached the
P&L and the computed net profit missed the account-121 balance by exactly
that amount. Map 7583 → Alte venituri exploatare and, proactively, its
expense pair 6583 (CHELT. PRIVIND ACTIVELE CEDATE) → Alte cheltuieli
exploatare so future disposals reconcile too.
"""

VERSION = 39
NAME = "0039_20260708_pnl_map_cedari_active"


def up(conn):
    conn.executemany(
        "INSERT OR IGNORE INTO pnl_mapping_conturi(cont,dencont,pnl_line,semn,categorie) "
        "VALUES(?,?,?,?,?)",
        [
            ('7583', 'VENITURI DIN CEDARI DE ACTIVE',
             'Alte venituri exploatare', 1, 'opex'),
            ('6583', 'CHELT. PRIVIND ACTIVELE CEDATE',
             'Alte cheltuieli exploatare', -1, 'opex'),
        ],
    )
