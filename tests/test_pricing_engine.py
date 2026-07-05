"""Pricing engine (F1): margin math, config thresholds, effective conditions."""
import pytest

import pricing_engine as pe
from db import get_db


# ── pure math ────────────────────────────────────────────────────────────────

def test_landing_cost_formula():
    # 10.5 USD * 4.6 = 48.3 RON, no transport/duty (FISIER_CONSOLIDAT example)
    assert pe.landing_cost(10.5, 4.6) == 48.3
    # 100 RON base + 10% transport + 5% duty + 2 RON other
    assert pe.landing_cost(100, 1, 10, 5, 2) == 117.0
    assert pe.landing_cost(None, 4.6) is None


def test_marja_is_relative_to_price():
    # owner convention: 48.3 -> 69 at 30% margin (margin of price, not markup)
    assert pe.marja_pct(69, 48.3) == 30.0
    assert pe.pret_pentru_marja(48.3, 30) == 69.0
    assert pe.marja_pct(0, 48.3) is None
    assert pe.marja_pct(None, 48.3) is None


def test_pret_pentru_marja_includes_conditions():
    # target 30% net with 11.72% conditions -> price covers 41.72% total
    pret = pe.pret_pentru_marja(48.3, 30, 11.72)
    assert pe.marja_neta_pct(pret, 48.3, 11.72) == pytest.approx(30.0, abs=0.01)
    assert pe.pret_pentru_marja(48.3, 60, 45) is None  # >=100% impossible


def test_marja_neta_subtracts_conditions():
    assert pe.marja_neta_pct(69, 48.3, 11.72) == pytest.approx(18.28)
    assert pe.marja_neta_pct(69, 48.3, None) == 30.0
    assert pe.marja_neta_pct(None, 48.3, 5) is None


def test_verdict_thresholds():
    praguri = {'minima': 30.0, 'aprobare': 25.0}
    assert pe.verdict(35, praguri) == 'ok'
    assert pe.verdict(30, praguri) == 'ok'
    assert pe.verdict(27, praguri) == 'atentie'
    assert pe.verdict(24.9, praguri) == 'aprobare_director'
    assert pe.verdict(None, praguri) is None


# ── pricing_config thresholds ────────────────────────────────────────────────

def test_praguri_default_from_migration_seed():
    p = pe.praguri_marja()
    assert p == {'minima': 30.0, 'aprobare': 25.0}


def test_praguri_per_gama_override():
    db = get_db()
    db.execute("INSERT OR REPLACE INTO pricing_config(gama, cheie, valoare) "
               "VALUES ('TORRAS', 'marja_minima_pct', '35')")
    db.commit()
    try:
        assert pe.praguri_marja('TORRAS') == {'minima': 35.0, 'aprobare': 25.0}
        assert pe.praguri_marja('BASILUR') == {'minima': 30.0, 'aprobare': 25.0}
        assert pe.praguri_marja() == {'minima': 30.0, 'aprobare': 25.0}
    finally:
        db.execute("DELETE FROM pricing_config WHERE gama='TORRAS'")
        db.commit()
        db.close()


# ── effective conditions with categorie/sku scope ────────────────────────────

def test_cond_effective_scope_sum():
    db = get_db()
    db.executescript("""
        DELETE FROM conditii_comerciale WHERE an = 2099;
        INSERT INTO conditii_comerciale(an, cod_client, furnizor, tip_valoare,
            periodicitate, valoare, descriere)
        VALUES
            (2099, 'C1', NULL, 'pct', 'anual', 10, 'client total'),
            (2099, 'C1', NULL, 'suma_fixa', 'anual', 5000, 'taxa listare'),
            (2099, 'C1', 'Basilur', 'pct', 'anual', 2, 'bonus brand'),
            (2099, NULL, NULL, 'pct', 'anual', 1, 'global toti clientii');
        UPDATE conditii_comerciale SET categorie='CEAI'
            WHERE an=2099 AND descriere='bonus brand';
    """)
    db.commit()
    try:
        # client-level only: 10 (client) + 1 (global); fixed sums excluded
        assert pe.cond_effective(2099, 'C1') == 11.0
        # brand+category scope adds the itemized 2%
        assert pe.cond_effective(2099, 'C1', 'Basilur', 'CEAI') == 13.0
        # different category: the CEAI-scoped row does not apply
        assert pe.cond_effective(2099, 'C1', 'Basilur', 'COSMETICE') == 11.0
        # unknown client: only the global row
        assert pe.cond_effective(2099, 'C2') == 1.0
    finally:
        db.execute("DELETE FROM conditii_comerciale WHERE an = 2099")
        db.commit()
        db.close()
