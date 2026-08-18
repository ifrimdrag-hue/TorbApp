"""Fuziuni de clienți (achiziții / rebranding) — mecanica de rescriere.

Maparea în sine stă în `app/business_constants.py` (`CLIENT_MERGES`); aici e
doar aplicarea ei. Cazul curent: Profi Rom Food SRL (cod_client 973) absorbit
de Mega Image SRL (4909).

ERP-ul continuă să exporte codul clientului absorbit pe rândurile istorice, iar
importul zilnic reconstruiește `tranzactii` de la zero — deci rescrierea nu se
poate face o singură dată, trebuie reaplicată la fiecare actualizare. De aceea
sunt două puncte de intrare:

  * `apply_record(record)` — la momentul importului, pe fiecare rând de
    tranzacție. Prinde și rularea directă a `import_vanzari_erp.py` (uploadul
    din pagina Actualizare Date), care nu trece prin `rebuild_db.py`.
  * `run(conn)` — o trecere idempotentă peste toate tabelele cu cod de client,
    apelată după rebuild și după importul de solduri. Repară și rândurile
    scrise înainte ca regula să existe.

Locația fizică (oraș, județ, adresă) nu se atinge: magazinele rămân unde sunt,
se schimbă doar identitatea comercială. Agentul rămâne cel din ERP.

Usage:
    python etl/client_merges.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from business_constants import CLIENT_MERGES  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = "data/torb.db"

# (tabel, coloana cu codul clientului, {coloană tabel: cheie din CLIENT_MERGES})
# Tabelele sau coloanele care lipsesc dintr-o bază sunt sărite tăcut, ca
# scriptul să meargă și pe o schemă mai veche.
CLIENT_TABLES = [
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


def norm_cod(val):
    """Forma canonică text a unui cod de client: 973.0 / 973 / ' 973 ' → '973'."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return str(int(float(s)))
    except ValueError:
        return s


def _cod_variants(cod):
    """Toate formele sub care codul poate fi stocat ('973', 973, '973.0').

    ERP-ul exportă codul ca număr, iar importurile îl scriu ca text, întreg sau
    float în funcție de script — comparăm cu toate.
    """
    variants = {cod}
    try:
        i = int(float(cod))
    except ValueError:
        return sorted(variants, key=str)
    variants |= {str(i), i, str(float(i))}
    return sorted(variants, key=str)


def apply_record(record):
    """Rescrie in-place identitatea clientului dintr-un rând de tranzacție.

    Întoarce True dacă rândul a fost rescris. `record` e un dict cu numele de
    coloane din `tranzactii`.
    """
    target = CLIENT_MERGES.get(norm_cod(record.get("cod_client")))
    if target is None:
        return False
    for col in ("client", "cod_client", "cui_client", "tip_client"):
        record[col] = target[col]
    return True


def _table_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _merge_table(conn, table, cod_col, ident, sursa_cod, target):
    """Mută rândurile unui tabel de la clientul absorbit la cel supraviețuitor.

    Întoarce (mutate, eliminate). `UPDATE OR IGNORE` lasă pe loc rândurile care
    ar încălca o cheie unică pe cod_client (tabelele de configurare au așa
    ceva): acolo clientul supraviețuitor are deja propria valoare, ea câștigă,
    iar rândul rămas al clientului absorbit se șterge — identitatea lui nu mai
    există.
    """
    cols = _table_columns(conn, table)
    if cod_col not in cols:
        return 0, 0

    variants = _cod_variants(sursa_cod)
    placeholders = ", ".join("?" * len(variants))
    where = f"WHERE {cod_col} IN ({placeholders})"

    before = conn.execute(
        f"SELECT COUNT(*) FROM {table} {where}", variants
    ).fetchone()[0]
    if not before:
        return 0, 0

    sets, params = [f"{cod_col} = ?"], [target["cod_client"]]
    for col, key in ident.items():
        if col in cols:
            sets.append(f"{col} = ?")
            params.append(target[key])
    conn.execute(
        f"UPDATE OR IGNORE {table} SET {', '.join(sets)} {where}", params + variants
    )

    dropped = conn.execute(f"DELETE FROM {table} {where}", variants).rowcount
    return before - dropped, dropped


def run(conn=None, verbose=True):
    """Aplică toate fuziunile de clienți pe întreaga bază. Idempotent.

    Întoarce {(cod_absorbit, tabel): (mutate, eliminate)} — doar tabelele
    atinse.
    """
    close_conn = conn is None
    if conn is None:
        conn = sqlite3.connect(DB_PATH)

    report = {}
    try:
        for sursa_cod, target in CLIENT_MERGES.items():
            for table, cod_col, ident in CLIENT_TABLES:
                moved, dropped = _merge_table(
                    conn, table, cod_col, ident, sursa_cod, target
                )
                if moved or dropped:
                    report[(sursa_cod, table)] = (moved, dropped)
        conn.commit()

        if verbose:
            if not report:
                print("    → Nicio fuziune de aplicat (deja aplicată sau client absent).")
            for (sursa_cod, table), (moved, dropped) in report.items():
                target = CLIENT_MERGES[sursa_cod]
                msg = (f"    → {table}: {moved:,} rânduri {target['sursa']}"
                       f" → {target['client']}")
                if dropped:
                    msg += f" ({dropped:,} eliminate — clientul țintă avea deja valoarea)"
                print(msg)
    finally:
        if close_conn:
            conn.close()

    return report


if __name__ == "__main__":
    run()
