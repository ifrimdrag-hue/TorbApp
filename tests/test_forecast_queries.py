"""Regression tests for app/queries/forecast.py — forecast page fixes."""
import sqlite3
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


def _conn(db_path):
    return sqlite3.connect(db_path)


def test_forecast_stoc_extended_includes_price(db_path, client):
    conn = _conn(db_path)
    conn.execute("""
        INSERT INTO stoc (data_snapshot, cod_produs, cod_mare, sku, furnizor, gama,
                           cantitate, pret_achizitie, data_intrare)
        VALUES ('2026-07-01', 'A5-001', 'A5-001', 'SKU-A5-001', 'TestBrandA5', 'Ceai',
                100, 10.0, '2026-06-01')
    """)
    conn.execute("""
        INSERT INTO costuri_landing (an, sku, moneda, pret_achizitie_valuta)
        VALUES (2026, 'SKU-A5-001', 'EUR', 3.5)
    """)
    conn.commit()
    conn.close()

    import queries
    rows = queries.forecast_stoc_extended(furnizor='TestBrandA5')
    assert len(rows) == 1
    assert rows[0]['pret_valuta'] == 3.5
    assert rows[0]['moneda_valuta'] == 'EUR'


def test_forecast_summary_counts_skus_not_lots(db_path, client):
    conn = _conn(db_path)
    # Same SKU, two lots (multi-lot SKU) — must count once, not twice
    conn.execute("""
        INSERT INTO stoc (data_snapshot, cod_produs, cod_mare, sku, furnizor, gama,
                           cantitate, pret_achizitie, data_intrare)
        VALUES ('2026-07-02', 'B1-001', 'B1-001', 'SKU-B1-MULTILOT', 'TestBrandB1', 'Ceai',
                10, 5.0, '2026-05-01')
    """)
    conn.execute("""
        INSERT INTO stoc (data_snapshot, cod_produs, cod_mare, sku, furnizor, gama,
                           cantitate, pret_achizitie, data_intrare)
        VALUES ('2026-07-02', 'B1-001', 'B1-001', 'SKU-B1-MULTILOT', 'TestBrandB1', 'Ceai',
                10, 5.0, '2026-06-01')
    """)
    conn.commit()
    conn.close()

    import queries
    summary = queries.forecast_summary()
    total_counted = (summary['critic'] or 0) + (summary['atentie'] or 0) + (summary['ok'] or 0)
    assert total_counted == summary['nr_sku'], (
        f"critic+atentie+ok ({total_counted}) must equal nr_sku ({summary['nr_sku']}) "
        "— a multi-lot SKU must count once"
    )
