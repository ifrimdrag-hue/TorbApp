"""
Migration 0032 — drop the Tobra rows inserted by the buggy 2026-07 import run.

Context: the Tobra->Auchan file is re-imported DAILY and covers the full
2024-2026 history, so any deleted TOBRA row is re-inserted (correctly, via
the cod-mare identity rule) on the next upload. Runs ONCE (versioned) — it
does not re-fire on subsequent deploys or daily imports.

Why delete instead of repair: the buggy run renamed its new rows via the
colliding cod_produs lookup. Migration 0031 repaired the ones that had prior
Auchan history to restore, but a renamed row for an article WITHOUT history
is indistinguishable from a real sale of the Torb article — unrecoverable in
place — and its dedup key (nr_dl, cod_produs, nr_factura) no longer matches
what the fixed import computes, so the next daily upload would insert the
correct row NEXT TO the wrong one (double counting). Dropping the whole
buggy-run cohort (TOBRA rows dated on/after 2026-06-01 — everything older
already existed before that run and was dedup-ignored by it) guarantees a
clean state after the next daily upload.
"""

VERSION = 32
NAME = "0032_20260707_tobra_buggy_cohort_cleanup"


def up(conn):
    conn.execute(
        "DELETE FROM tranzactii WHERE cod_client = '732' "
        "AND nr_factura LIKE 'TOBRA%' AND data_dl >= '2026-06-01'"
    )
