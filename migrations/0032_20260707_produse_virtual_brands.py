"""
Migration 0032 — produse catalog: virtual sub-brands get their own furnizor.

The monitorizare spreadsheet lists KingsLeaf/Tipson articles with
Furnizor=Basilur (the real supplier) and the sub-brand only in the Brand
column ('KINGSLEAF', 'TIPSON TEA'), so import_preturi filed 54 KingsLeaf and
56 Tipson catalog articles under furnizor='Basilur' / gama='Basilur'.
The import now normalizes via the Brand column; this migration reclassifies
the existing rows the same way (brand-column driven, so it also catches
description typos like 'KINSGELAF' and the CHRISTMAS-named KL articles).
Idempotent.
"""

VERSION = 32
NAME = "0032_20260707_produse_virtual_brands"

RULES = [
    ("KingsLeaf", ("KINGSLEAF", "KINGS LEAF")),
    ("Tipson", ("TIPSON", "TIPSON TEA")),
    ("Organsia", ("ORGANSIA",)),
]


def up(conn):
    for canon, spellings in RULES:
        placeholders = ",".join("?" * len(spellings))
        conn.execute(
            f"UPDATE produse SET furnizor = ?, brand = ?, gama = ? "
            f"WHERE furnizor <> ? AND UPPER(brand) IN ({placeholders})",
            (canon, canon, canon, canon, *spellings),
        )
