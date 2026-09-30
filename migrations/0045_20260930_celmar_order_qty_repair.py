"""
Migration 0045 — repair Celmar order lines imported with shifted columns.

The Celmar Order Form dropped a column in Aug 2026 (NEW_ORDER_30_12.08.2026):
'Order pcs' moved to index 4 and 'TOTAL Value (PLN)' to index 5. The importer
read fixed indices, so every line stored the PLN value as cantitate_comandata,
the real piece count as cantitate_baxuri, and total_valuta = price x value.
The importer now locates columns by header text; this repairs the stored lines.

A shifted line is recognisable from its own numbers: cantitate_comandata equals
pret_valuta x cantitate_baxuri (value = price x pieces, within the int()
truncation of the import). A correct line holds pallets in cantitate_baxuri, so
it could only match at a price of ~pcs_per_pallet PLN. Only file-imported
Celmar orders are considered (manual orders have no file_source).
Idempotent: a repaired line no longer matches.
"""

VERSION = 45
NAME = "0045_20260930_celmar_order_qty_repair"


def up(conn):
    rows = conn.execute("""
        SELECT l.id, l.comanda_id, l.cantitate_baxuri, l.units_per_carton, l.pret_valuta
        FROM comenzi_furnizori_linii l
        JOIN comenzi_furnizori c ON c.id = l.comanda_id
        WHERE c.furnizor = 'Celmar' AND c.file_source IS NOT NULL
          AND l.pret_valuta > 0 AND l.cantitate_baxuri > 0
          AND ABS(l.cantitate_comandata - l.pret_valuta * l.cantitate_baxuri) <= 1
    """).fetchall()
    for line_id, _, pcs, per_pallet, price in rows:
        conn.execute(
            "UPDATE comenzi_furnizori_linii "
            "SET cantitate_comandata = ?, cantitate_baxuri = ?, total_valuta = ? "
            "WHERE id = ?",
            (int(round(pcs)), round(pcs / per_pallet, 4) if per_pallet else None,
             round(price * pcs, 2), line_id),
        )
    for comanda_id in {r[1] for r in rows}:
        conn.execute(
            "UPDATE comenzi_furnizori SET total_usd = ("
            "  SELECT ROUND(SUM(total_valuta), 2) FROM comenzi_furnizori_linii"
            "  WHERE comanda_id = ?) WHERE id = ?",
            (comanda_id, comanda_id),
        )
