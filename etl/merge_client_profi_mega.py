"""
Excepție business: Profi Rom Food SRL a fost achiziționat de Mega Image SRL.
Tot istoricul Profi (cod_client='973') este reatribuit către Mega Image (cod_client='4909').

Logică:
- Actualizează client, cod_client, cui_client, tip_client în tranzactii
- Păstrează oras_client, judet_client, adresa_client (locații fizice ale magazinelor)
- Păstrează agent (deja Oana Filip pentru ambii)
- Idempotent: rulat de mai multe ori produce același rezultat

Usage:
    python merge_client_profi_mega.py
"""

import sqlite3
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "data/torb.db"

PROFI_COD_CLIENT  = "973"
MEGA_COD_CLIENT   = "4909"
MEGA_CLIENT       = "MEGA IMAGE SRL"
MEGA_CUI          = "RO6719278"
MEGA_TIP_CLIENT   = "SUPERMARKET"


def run(conn=None):
    close_conn = conn is None
    if conn is None:
        conn = sqlite3.connect(DB_PATH)

    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(val_neta), 0) FROM tranzactii WHERE cod_client = ?",
        (PROFI_COD_CLIENT,),
    )
    n, val = cur.fetchone()

    if n == 0:
        print("    → Nicio tranzacție Profi Rom Food de migrat (deja migrat sau absent).")
        if close_conn:
            conn.close()
        return 0

    cur.execute(
        """UPDATE tranzactii
           SET client     = ?,
               cod_client = ?,
               cui_client = ?,
               tip_client = ?
           WHERE cod_client = ?""",
        (MEGA_CLIENT, MEGA_COD_CLIENT, MEGA_CUI, MEGA_TIP_CLIENT, PROFI_COD_CLIENT),
    )
    conn.commit()

    print(
        f"    → {n:,} tranzacții Profi Rom Food migrate → Mega Image SRL"
        f" ({val:,.0f} RON)"
    )

    cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(val_neta), 0), MIN(data_dl), MAX(data_dl)"
        " FROM tranzactii WHERE cod_client = ?",
        (MEGA_COD_CLIENT,),
    )
    total_n, total_val, d_min, d_max = cur.fetchone()
    print(
        f"    → Total Mega Image în DB: {total_n:,} tranz"
        f" | {total_val:,.0f} RON | {d_min} → {d_max}"
    )

    if close_conn:
        conn.close()
    return n


if __name__ == "__main__":
    run()
