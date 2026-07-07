"""Migration 0036 — consolidate duplicate produse rows (EAN-as-SKU twins).

The tranzactii backfill in import_preturi.py created an EAN-as-SKU produse row
(sku = bare 13-digit EAN, real product name, ean NULL) for suppliers whose
transactions use the long concatenated SKU (Solvex, Toras), even though a
master row already exists for that product (sku = numeric code, placeholder
descriere 'Articol cod NNN', carrying the real ean + buc_cutie + landing
costs). That produced ~29 twin rows.

Fold each EAN-as-SKU twin into its master:
  1. copy the real product name onto the master (only if still a placeholder),
  2. move selling prices to the master SKU — skip on conflict so the master's
     Monitorizare list price wins over the twin's historical-average price,
  3. delete the twin produse row.

The catalog resolver (queries/_shared.resolve_catalog_sku) maps the long
transaction SKU to the master via its `ean` column, so removing the twin does
not break sales<->catalog resolution. The importer fix in the same change stops
new twins from being created.
"""

VERSION = 36
NAME = "0036_20260707_produse_dedup_ean_twins"


def up(conn):
    pairs = conn.execute("""
        SELECT p.sku AS ean_sku, q.sku AS code_sku, p.descriere AS real_name
        FROM produse p
        JOIN produse q ON q.ean = p.sku AND q.sku <> p.sku
        WHERE p.sku GLOB '[0-9]*' AND length(p.sku) BETWEEN 8 AND 13
    """).fetchall()
    for ean_sku, code_sku, real_name in pairs:
        if real_name:
            conn.execute(
                "UPDATE produse SET descriere = ? "
                "WHERE sku = ? AND (descriere LIKE 'Articol cod %' "
                "                   OR descriere IS NULL OR descriere = '')",
                (real_name, code_sku),
            )
        # move prices where the master has none for that (an[, cod_client]); the
        # unique indexes make UPDATE OR IGNORE skip conflicts, then drop leftovers
        conn.execute("UPDATE OR IGNORE preturi_vanzare SET sku = ? WHERE sku = ?",
                     (code_sku, ean_sku))
        conn.execute("DELETE FROM preturi_vanzare WHERE sku = ?", (ean_sku,))
        conn.execute("DELETE FROM produse WHERE sku = ?", (ean_sku,))
