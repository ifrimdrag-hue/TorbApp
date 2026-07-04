"""Multi-country export model (owner item 2, 2026-07-04).

Countries/allocations are data (tari_export/clienti_export) — markets reach
pair_engine as row['market'] (already resolved from DB in _fetch_rows), so
profiles and the order split must handle any number of country keys.
Owner decision: export countries get NO stock offset — available stock covers
RO only; each country orders its full coverage demand + safety.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from forecast import pair_engine as pe  # noqa: E402
from forecast import forecast_logic as fl  # noqa: E402

PARAMS = {"fereastra_luni": 36, "sezonalitate_min_luni": 24,
          "indice_sezonier_min": 0.2, "indice_sezonier_max": 5.0,
          "prag_delistare_zile": 180, "prag_delistare_mult": 3}


def _rows_two_countries():
    """RO client 100/mo, HU client 50/mo, MD client 20/mo — 4 closed months."""
    rows = []
    for (y, m) in [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]:
        rows.append({"cod_client": "CRO", "client": "Client RO", "sku": "S",
                     "cod_produs": "1", "market": "ro",
                     "d": date(y, m, 10), "qty": 100.0})
        rows.append({"cod_client": "CHU", "client": "Client HU", "sku": "S",
                     "cod_produs": "1", "market": "HU",
                     "d": date(y, m, 12), "qty": 50.0})
        rows.append({"cod_client": "CMD", "client": "Client MD", "sku": "S",
                     "cod_produs": "1", "market": "MD",
                     "d": date(y, m, 14), "qty": 20.0})
    return rows


def test_profiles_have_per_country_markets():
    today = date(2026, 7, 15)
    prof = pe.article_monthly_profiles("X", PARAMS, today=today,
                                       _rows=_rows_two_countries())
    s = prof["S"]
    assert set(s["piete"].keys()) == {"HU", "MD"}
    assert round(s["ro"][7], 1) == 100.0
    assert round(s["piete"]["HU"][7], 1) == 50.0
    assert round(s["piete"]["MD"][7], 1) == 20.0
    # 'export' stays the cross-country sum (backward compatibility)
    assert round(s["export"][7], 1) == 70.0
    assert round(s["total"][7], 1) == 170.0


def test_split_multi_country_no_stock_offset():
    monthly_ro = {m: 30.0 for m in range(1, 13)}
    monthly_hu = {m: 15.0 for m in range(1, 13)}
    monthly_md = {m: 6.0 for m in range(1, 13)}
    piete = {"HU": monthly_hu, "MD": monthly_md}
    monthly_exp = {m: monthly_hu[m] + monthly_md[m] for m in range(1, 13)}
    lead, coverage = 30, 30
    demand_ro = fl._coverage_demand(monthly_ro, lead, coverage)

    # Stock far beyond RO demand: RO suggestion 0, but countries STILL order
    # their full demand+safety (no surplus offset — owner decision).
    huge = demand_ro + 10_000
    s = fl.split_with_safety(monthly_ro, monthly_exp, lead, huge,
                             30.0, 21.0, 0.0, coverage, None,
                             monthly_piete=piete)
    assert s["suggested_ro"] == 0
    assert s["piete"]["HU"]["suggested"] == round(
        fl._coverage_demand(monthly_hu, lead, coverage))
    assert s["piete"]["MD"]["suggested"] == round(
        fl._coverage_demand(monthly_md, lead, coverage))
    assert s["suggested_export"] == (s["piete"]["HU"]["suggested"]
                                     + s["piete"]["MD"]["suggested"])


def test_split_legacy_mode_unchanged_without_piete():
    monthly_ro = {m: 30.0 for m in range(1, 13)}
    monthly_exp = {m: 15.0 for m in range(1, 13)}
    lead, coverage = 30, 30
    demand_ro = fl._coverage_demand(monthly_ro, lead, coverage)
    # Legacy: surplus beyond RO offsets the export order.
    s = fl.split_with_safety(monthly_ro, monthly_exp, lead, demand_ro + 5,
                             30.0, 15.0, 0.0, coverage, None)
    assert s["suggested_ro"] == 0
    expected = max(0.0, fl._coverage_demand(monthly_exp, lead, coverage) - 5)
    assert abs(s["suggested_export"] - round(expected)) <= 1
    assert s["piete"] == {}


def test_split_zero_country_demand_gives_zero():
    monthly_ro = {m: 30.0 for m in range(1, 13)}
    s = fl.split_with_safety(monthly_ro, {}, 30, 0, 30.0, 0.0, 0.25, 30, None,
                             monthly_piete={"HU": {}})
    assert s["piete"]["HU"]["suggested"] == 0
    assert s["suggested_export"] == 0


def test_tari_export_accepts_any_market_code(db_path):
    """Migration 0020: the CHECK(piata IN ('RO','HU')) from 0001 is gone —
    adding a country with any short code (BG, AT, MD...) must work, and
    existing rows/ids must survive the table rebuild."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        # Seeded 'Ungaria' survived the rebuild with its id/piata intact.
        assert conn.execute(
            "SELECT piata FROM tari_export WHERE tara='Ungaria'"
        ).fetchone()[0] == 'HU'
        conn.execute(
            "INSERT INTO tari_export (tara, piata) VALUES ('Bulgaria', 'BG')")
        conn.commit()
        assert conn.execute(
            "SELECT piata FROM tari_export WHERE tara='Bulgaria'"
        ).fetchone()[0] == 'BG'
    finally:
        conn.execute("DELETE FROM tari_export WHERE tara='Bulgaria'")
        conn.commit()
        conn.close()


def test_order_line_piete_roundtrip(client, db_path):
    """Per-country order quantities persist via comenzi_linii_piete (mig 0019)."""
    import queries
    cid = queries.comanda_create('Basilur', nr_comanda='TEST-PIETE')
    try:
        queries.comanda_line_upsert(
            cid, 'SKU-PIETE-1', 30, cantitate_ro=10,
            cantitati_piete={'HU': 15, 'MD': 5})
        data = queries.comanda_get(cid)
        line = next(ln for ln in data['lines'] if ln['sku'] == 'SKU-PIETE-1')
        assert line['cantitati_piete'] == {'HU': 15, 'MD': 5}
        # cantitate_export kept in sync with the per-country sum
        assert line['cantitate_export'] == 20
        # re-upsert replaces the breakdown (no stale rows)
        queries.comanda_line_upsert(
            cid, 'SKU-PIETE-1', 22, cantitate_ro=10,
            cantitati_piete={'HU': 12})
        line = next(ln for ln in queries.comanda_get(cid)['lines']
                    if ln['sku'] == 'SKU-PIETE-1')
        assert line['cantitati_piete'] == {'HU': 12}
        assert line['cantitate_export'] == 12
    finally:
        queries.comanda_delete(cid)
