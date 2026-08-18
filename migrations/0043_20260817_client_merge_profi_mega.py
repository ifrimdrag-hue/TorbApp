"""
Migration 0043 — carry the Profi Rom Food → Mega Image merger into the tables
the daily rebuild never touches.

Profi Rom Food SRL (cod_client 973) was acquired by Mega Image SRL (4909).
`tranzactii` is rebuilt from the ERP export on every update and the ETL now
rewrites the absorbed client at import time (etl/client_merges.py), but the
configuration and balance tables survive a rebuild, so rows written before the
rule existed still carry code 973. Move them once here.

Tables with a UNIQUE key on cod_client can already hold a Mega Image row for
the same key: `UPDATE OR IGNORE` leaves the Profi row in place there, and the
surviving client's own value wins — the leftover is deleted, since the absorbed
client no longer exists. Idempotent; skips tables/columns not present.
"""

VERSION = 43
NAME = "0043_20260817_client_merge_profi_mega"

PROFI_COD = "973"
# Every form the code can be stored in: ERP exports it as a number, the import
# scripts write text, int or float depending on the script.
PROFI_VARIANTS = (PROFI_COD, 973, "973.0")

MEGA = {
    "cod_client": "4909",
    "client":     "MEGA IMAGE SRL",
    "cui_client": "RO6719278",
    "tip_client": "SUPERMARKET",
}

# (table, cod column, {table column: key in MEGA})
TABLES = [
    ("tranzactii",            "cod_client", {"client":  "client",
                                             "cui_client": "cui_client",
                                             "tip_client": "tip_client"}),
    ("solduri_neincasate",    "codcli",     {"numecli": "client",
                                             "cfcli":   "cui_client"}),
    ("conditii_comerciale",   "cod_client", {}),
    ("cond_resolved",         "cod_client", {}),
    ("termene_plata",         "cod_client", {}),
    ("preturi_vanzare",       "cod_client", {}),
    ("coduri_client_articol", "cod_client", {}),
    ("clienti_pricing",       "cod_client", {}),
    ("propuneri_pret",        "cod_client", {}),
]


def up(conn):
    placeholders = ", ".join("?" * len(PROFI_VARIANTS))
    for table, cod_col, ident in TABLES:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if cod_col not in cols:
            continue
        where = f"WHERE {cod_col} IN ({placeholders})"

        sets, params = [f"{cod_col} = ?"], [MEGA["cod_client"]]
        for col, key in ident.items():
            if col in cols:
                sets.append(f"{col} = ?")
                params.append(MEGA[key])

        conn.execute(
            f"UPDATE OR IGNORE {table} SET {', '.join(sets)} {where}",
            params + list(PROFI_VARIANTS),
        )
        conn.execute(f"DELETE FROM {table} {where}", PROFI_VARIANTS)
