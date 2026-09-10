"""The Basilur report values sales at purchase price, not at selling price.

These guard the basis itself: a sales or stock update (import_vanzari_erp.py,
import_vanzari_tobra_auchan.py, import_stoc.py) must never move the report
back onto val_neta, and a row missing val_achizitie must fall back to the
cost implied by marja_bruta rather than count as zero.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

AN = 2031          # far from any other fixture's year
BRAND = 'Basilur'


def _seed(conn, rows):
    conn.executemany("""
        INSERT INTO tranzactii (an, luna, furnizor, cod_client, cod_produs, sku,
                                cantitate, pret_vanzare, pret_cumparare,
                                val_neta, val_achizitie, marja_bruta)
        VALUES (:an, :luna, :furnizor, :cod_client, :cod_produs, :sku,
                :cantitate, :pret_vanzare, :pret_cumparare,
                :val_neta, :val_achizitie, :marja_bruta)
    """, rows)
    conn.commit()


def _row(luna, val_neta, val_achizitie, cod_client=9001, an=AN, marja=None):
    return {
        'an': an, 'luna': luna, 'furnizor': BRAND, 'cod_client': cod_client,
        'cod_produs': 'BAS-COST-1', 'sku': 'B.TEST COST',
        'cantitate': 10, 'pret_vanzare': 10.0, 'pret_cumparare': 4.0,
        'val_neta': val_neta, 'val_achizitie': val_achizitie,
        'marja_bruta': marja if marja is not None
        else (val_neta - (val_achizitie or 0)),
    }


def test_kpi_sums_purchase_value_not_net_value(db_path, client):
    conn = sqlite3.connect(db_path)
    _seed(conn, [_row(3, 1000.0, 400.0), _row(4, 500.0, 200.0)])
    conn.close()

    import queries
    total = queries.basilur_kpi_total(AN)
    assert total['val_achizitie'] == 600      # 400 + 200, not 1500
    per_brand = {r['furnizor']: r for r in queries.basilur_kpi_per_brand(AN)}
    assert per_brand[BRAND]['val_achizitie'] == 600
    monthly = {(r['furnizor'], r['luna']): r for r
               in queries.basilur_monthly_per_brand(AN)}
    assert monthly[(BRAND, 3)]['val_achizitie'] == 400
    assert monthly[(BRAND, 4)]['val_achizitie'] == 200


def test_yoy_delta_compares_purchase_values(db_path, client):
    """PY sales at cost drive the delta — a margin change must not move it."""
    conn = sqlite3.connect(db_path)
    # PY: same 300 at cost, but a much wider selling margin than CY.
    _seed(conn, [_row(5, 9999.0, 300.0, cod_client=9002, an=AN + 9),
                 _row(5, 700.0, 600.0, cod_client=9002, an=AN + 10)])
    conn.close()

    import queries
    total = queries.basilur_kpi_total(AN + 10)
    assert total['val_achizitie'] == 600
    assert total['val_achizitie_py'] == 300
    assert total['delta_vn'] == 100.0     # 600 vs 300, not 700 vs 9999


def test_row_without_val_achizitie_falls_back_to_margin(db_path, client):
    """Legacy rows carry marja_bruta but no Val_Achiz column — the implied
    cost (val_neta - marja_bruta) must be counted, not zero."""
    conn = sqlite3.connect(db_path)
    _seed(conn, [_row(6, 1000.0, None, cod_client=9003, an=AN + 1, marja=250.0)])
    conn.close()

    import queries
    total = queries.basilur_kpi_total(AN + 1)
    assert total['val_achizitie'] == 750      # 1000 - 250, not 0


def test_sales_import_refreshes_the_cost_columns_on_reupload():
    """Re-uploading a sales file updates val_achizitie / marja_bruta in place.

    import_vanzari_erp.insert_rows() upserts on (nr_dl, cod_produs, nr_factura,
    pret_vanzare); if the cost columns were left out of the UPDATE set, a
    corrected re-upload would keep the old basis and the report would drift.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'etl'))
    import import_vanzari_erp as erp
    assert 'val_achizitie' in erp._UPDATE_COLS
    assert 'marja_bruta' in erp._UPDATE_COLS
