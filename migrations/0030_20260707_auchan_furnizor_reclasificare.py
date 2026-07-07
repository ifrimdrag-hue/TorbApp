"""
Migration 0030 — reclassify Auchan (Tobra-imported) furnizor by SKU name.

The Tobra->Auchan import resolved furnizor through a cod_produs lookup built
from Torb ERP rows, but Tobra's cod_produs numbering collides with Torb's
(e.g. Tobra 1508 = 'KL ENGLISH BREAKFAST' vs Torb 1508 = 'C.GOPLANA'/Celmar).
That put KingsLeaf tea under Celmar/Basilur and Toras chocolate under
Basilur/Solvex for cod_client 732 (~325k RON misattributed, 2024-2026).

Re-apply the deterministic SKU-name prefix rules (same order as
etl/import_vanzari_tobra_auchan.py, which now checks them before the lookup)
to Auchan rows only. Rows whose stored furnizor already matches are untouched;
rows with no matching prefix rule keep their lookup-derived furnizor.
Idempotent.
"""

VERSION = 30
NAME = "0030_20260707_auchan_furnizor_reclasificare"

AUCHAN_COD_CLIENT = "732"

# (target furnizor, SQL condition on sku) — same priority order as the ETL's
# _furnizor_from_sku_name(); each UPDATE excludes rows already claimed by an
# earlier rule via the NOT-conditions baked into the patterns below.
RULES = [
    ("Organsia", "sku LIKE 'B.ECO ORGANSIA%'"),
    ("Basilur", "(sku LIKE 'B.%' OR sku LIKE 'WB.%') AND sku NOT LIKE 'B.ECO ORGANSIA%'"),
    ("KingsLeaf", "sku LIKE 'KL %'"),
    ("Celmar", "sku LIKE 'CELMAR%' OR sku LIKE 'C.%' OR sku LIKE '%5902795%' OR sku LIKE '%5902480%'"),
    ("Toras", "sku LIKE 'T.%'"),
    ("Tipson", "sku LIKE 'TS %'"),
    ("Delaviuda", "sku LIKE 'DEL.%' OR sku LIKE 'ALM.%'"),
]


def up(conn):
    for furnizor, cond in RULES:
        conn.execute(
            f"UPDATE tranzactii SET furnizor = ? "
            f"WHERE cod_client = ? AND furnizor <> ? AND ({cond})",
            (furnizor, AUCHAN_COD_CLIENT, furnizor),
        )
