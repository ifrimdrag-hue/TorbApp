"""
Migration 0012 — Organsia virtual brand.

Seed termene_aprovizionare lead time for Organsia (mirror Basilur: 120 zile,
sezon Crăciun, USD, Ceai) and reclassify historical rows currently mis-tagged
as Basilur (SKUs whose name starts with 'B.ECO ORGANSIA') across stoc,
tranzactii and produse. Idempotent.
"""

VERSION = 12
NAME = "0012_20260701_organsia_brand"


def up(conn):
    conn.execute(
        "INSERT OR IGNORE INTO termene_aprovizionare "
        "(furnizor, zile_livrare, sezon_craciun, observatii, zile_livrare_min, moneda, tip_produs) "
        "VALUES ('Organsia', 120, 1, 'Produse sezoniere Crăciun — comandă Apr-Mai', 120, 'USD', 'Ceai')"
    )
    conn.execute(
        "UPDATE stoc SET furnizor='Organsia' "
        "WHERE furnizor='Basilur' AND sku LIKE 'B.ECO ORGANSIA%'"
    )
    conn.execute(
        "UPDATE stoc SET gama='Organsia' "
        "WHERE furnizor='Organsia' AND (gama IS NULL OR gama='Basilur')"
    )
    conn.execute(
        "UPDATE tranzactii SET furnizor='Organsia' "
        "WHERE furnizor='Basilur' AND sku LIKE 'B.ECO ORGANSIA%'"
    )
    conn.execute(
        "UPDATE produse SET furnizor='Organsia', brand='Organsia', gama='Organsia' "
        "WHERE furnizor='Basilur' AND descriere LIKE 'ORGANSIA%'"
    )
