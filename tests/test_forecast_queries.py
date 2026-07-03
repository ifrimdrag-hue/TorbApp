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


def test_zile_stoc_excludes_transit(db_path, client):
    conn = _conn(db_path)
    conn.execute("""
        INSERT INTO stoc (data_snapshot, cod_produs, cod_mare, sku, furnizor, gama,
                           cantitate, pret_achizitie, data_intrare)
        VALUES ('2026-07-03', 'B2-001', 'B2-001', 'SKU-B2-001', 'TestBrandB2', 'Ceai',
                30, 10.0, '2026-06-01')
    """)
    # 3 years of sales so the 3-year monthly average kicks in and overwrites zile_stoc
    for luna in range(1, 13):
        conn.execute("""
            INSERT INTO tranzactii (luna, an, data_dl, sku, furnizor, cantitate,
                                     cod_produs, client, cod_client, agent,
                                     pret_vanzare, tva_pct, pret_cumparare,
                                     val_bruta, val_neta, val_achizitie, marja_bruta, discount_pct)
            VALUES (:luna, 2025, '2025-' || printf('%02d', :luna) || '-10',
                    'SKU-B2-001', 'TestBrandB2', 30,
                    'B2-001', 'Client Test', 'C001', 'Agent Test',
                    10, 0.09, 5, 300, 275, 150, 125, 0)
        """, {'luna': luna})
    # An active in-transit order for the same SKU — must NOT reduce zile_stoc
    conn.execute("""
        INSERT INTO comenzi_furnizori (nr_comanda, furnizor, status, data_estimata_livrare)
        VALUES ('CMD-B2-1', 'TestBrandB2', 'confirmata', '2026-08-01')
    """)
    cid = conn.execute("SELECT id FROM comenzi_furnizori WHERE nr_comanda='CMD-B2-1'").fetchone()[0]
    conn.execute("""
        INSERT INTO comenzi_furnizori_linii (comanda_id, sku, cantitate_comandata)
        VALUES (?, 'SKU-B2-001', 30)
    """, (cid,))
    conn.commit()
    conn.close()

    import queries
    rows = queries.forecast_stoc_extended(furnizor='TestBrandB2')
    assert len(rows) == 1
    r = rows[0]
    # 30 avg/month sales -> daily rate 1/day -> stoc-only zile_stoc should be ~30 (30 buc / 1 buc/day)
    # If transit (30 more) were included, available=60 -> zile_stoc would be ~60
    assert r['zile_stoc'] < 45, (
        f"zile_stoc={r['zile_stoc']} appears to include the 30-unit in-transit order "
        "(physical stock alone should give ~30 days, not ~60)"
    )
