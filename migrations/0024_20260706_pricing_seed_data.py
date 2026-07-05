"""Migration 0024 - seed pricing data validated locally (F0/F1 import).

The pricing import sources (FISIER_CONSOLIDAT, RO1 order forms) are
commercial Excel files that never enter git, and there is no SSH path to
dev/prod. This migration carries the validated result rows instead
(migrations/data/0024_pricing_seed.json) so the owner can validate the
module on dev :5001 with real data.

Idempotent: INSERT OR IGNORE against each table's unique key - existing
rows on the target DB always win, nothing is overwritten.
"""
import json
from pathlib import Path

VERSION = 24
NAME = "0024_20260706_pricing_seed_data"

_SEED = Path(__file__).parent / "data" / "0024_pricing_seed.json"

_TABLES = {
    "costuri_landing": (
        "an", "sku", "moneda", "pret_achizitie_valuta", "curs_ron",
        "pret_achizitie_ron", "transport_pct", "taxa_vamala_pct",
        "alte_costuri_ron", "landing_cost_ron"),
    "preturi_vanzare": ("an", "sku", "cod_client", "pret_vanzare_ron", "activ"),
    "coduri_client_articol": ("sku", "cod_client", "cod_intern", "cod_intern2", "sursa"),
    "produse_logistica": (
        "sku", "unit_l_mm", "unit_w_mm", "unit_h_mm", "unit_net_kg",
        "unit_gross_kg", "bax_l_mm", "bax_w_mm", "bax_h_mm", "bax_gross_kg",
        "bax_cbm", "buc_bax", "bax_palet", "valabilitate_luni", "moq", "sursa"),
    "conditii_comerciale": (
        "an", "cod_client", "furnizor", "tip_valoare", "periodicitate",
        "valoare", "descriere", "data_creare", "categorie", "sku"),
    "clienti_pricing": (
        "cod_client", "nume_client", "marja_raft_pct", "template_listare", "activ"),
}


def up(conn):
    if conn.execute("SELECT COUNT(*) FROM produse").fetchone()[0] == 0:
        return  # empty catalog (fresh/test DB) - nothing to seed against
    seed = json.loads(_SEED.read_text(encoding="utf-8"))
    inserted_cond = 0
    for table, cols in _TABLES.items():
        rows = seed.get(table, [])
        if not rows:
            continue
        sql = (f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) "
               f"VALUES ({', '.join('?' * len(cols))})")
        for r in rows:
            if table == "conditii_comerciale":
                # no unique key on this table - seed a client only if it has
                # no pct conditions for the year yet
                exists = conn.execute(
                    "SELECT 1 FROM conditii_comerciale WHERE an=? AND "
                    "cod_client=? AND tip_valoare='pct' LIMIT 1",
                    (r.get("an"), r.get("cod_client"))).fetchone()
                if exists:
                    continue
                inserted_cond += 1
            conn.execute(sql, tuple(r.get(c) for c in cols))
    if inserted_cond:
        # freshly seeded conditions -> let the app rebuild the materialized
        # table lazily at startup (ensure_cond_resolved)
        conn.execute("DELETE FROM cond_resolved")
