"""
Migration 0029 — HORECA formats of the virtual sub-brands keep their own brand.

The generic 'HORECA ' -> Basilur rule fired before any virtual-brand check, so
Tipson HORECA products ('HORECA TS ...', ERP code range 80xxx) were filed under
Basilur in tranzactii and produse (9 SKUs). The ETL derivation functions now
check 'HORECA TS ' / 'HORECA KL ' / 'HORECA ORGANSIA' first; this migration
reclassifies the existing rows the same way. stoc currently has no such rows,
updated anyway for symmetry. Idempotent.
"""

VERSION = 29
NAME = "0029_20260707_horeca_virtual_brands"

RULES = [
    ("Tipson", "HORECA TS %", "H TS %"),
    ("KingsLeaf", "HORECA KL %", "H KL %"),
    ("Organsia", "HORECA ORGANSIA%", "HORECA B.ECO ORGANSIA%"),
]


def up(conn):
    for furnizor, p1, p2 in RULES:
        conn.execute(
            "UPDATE tranzactii SET furnizor = ? "
            "WHERE furnizor <> ? AND (sku LIKE ? OR sku LIKE ?)",
            (furnizor, furnizor, p1, p2),
        )
        conn.execute(
            "UPDATE stoc SET furnizor = ?, gama = ? "
            "WHERE furnizor <> ? AND (sku LIKE ? OR sku LIKE ?)",
            (furnizor, furnizor, furnizor, p1, p2),
        )
        conn.execute(
            "UPDATE produse SET furnizor = ?, brand = ?, gama = ? "
            "WHERE furnizor <> ? AND (descriere LIKE ? OR descriere LIKE ?)",
            (furnizor, furnizor, furnizor, furnizor, p1, p2),
        )
