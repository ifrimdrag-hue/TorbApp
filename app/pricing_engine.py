"""Pricing engine (F1) - cost and margin math for the pricing module.

Conventions (owner decisions, docs/plans/2026-07-05-modul-pricing-ofertare.md):
  - margin is relative to the selling price: marja = (pret - landing) / pret
    (FISIER_CONSOLIDAT: landing 48.3 -> "pret baza 30%" 69 = 48.3 / 0.7)
  - commercial conditions are % of the invoiced value, so
    net margin % = gross margin % - effective conditions %
    (fixed-amount conditions are yearly lump sums, settled at client P&L
    level - decision #12 - not per unit, so they are excluded here)
  - margin thresholds are DATA in pricing_config (global row gama='',
    optional per-gama override), never constants in code.

Pure math functions take plain numbers; DB lookups go through db.query so
they work both inside Flask and in scripts.
"""
from db import query

# pricing_config keys
_K_MIN = 'marja_minima_pct'
_K_APR = 'marja_aprobare_pct'


# ── pure math ────────────────────────────────────────────────────────────────

def landing_cost(pret_valuta, curs, transport_pct=0.0, taxa_vamala_pct=0.0,
                 alte_costuri_ron=0.0):
    """RON landing cost; same formula as queries.preturi_update_landing."""
    if pret_valuta is None or curs is None:
        return None
    pret_ron = pret_valuta * curs
    return round(pret_ron * (1 + (transport_pct or 0) / 100)
                 + pret_ron * (taxa_vamala_pct or 0) / 100
                 + (alte_costuri_ron or 0), 4)


def marja_pct(pret_ron, landing_ron):
    """Gross margin % of the selling price. None when not computable."""
    if not pret_ron or landing_ron is None:
        return None
    return round((pret_ron - landing_ron) / pret_ron * 100, 2)


def marja_neta_pct(pret_ron, landing_ron, cond_pct=0.0):
    """Net margin % after commercial conditions (% of invoiced value)."""
    brut = marja_pct(pret_ron, landing_ron)
    if brut is None:
        return None
    return round(brut - (cond_pct or 0), 2)


def pret_pentru_marja(landing_ron, marja_tinta_pct, cond_pct=0.0):
    """Selling price that yields the target NET margin after conditions."""
    if landing_ron is None:
        return None
    total = (marja_tinta_pct or 0) + (cond_pct or 0)
    if total >= 100:
        return None
    return round(landing_ron / (1 - total / 100), 4)


def verdict(marja_neta, praguri):
    """'ok' / 'atentie' (below floor) / 'aprobare_director' (below approval)."""
    if marja_neta is None:
        return None
    if marja_neta < praguri['aprobare']:
        return 'aprobare_director'
    if marja_neta < praguri['minima']:
        return 'atentie'
    return 'ok'


# ── config / conditions lookups ──────────────────────────────────────────────

def praguri_marja(gama=None):
    """Margin thresholds {'minima', 'aprobare'}; per-gama override -> global."""
    rows = query(
        "SELECT gama, cheie, valoare FROM pricing_config "
        "WHERE cheie IN (:k1, :k2) AND gama IN ('', :gama)",
        {"k1": _K_MIN, "k2": _K_APR, "gama": gama or ''})
    vals = {}
    for r in rows:  # global first, then override
        key = 'minima' if r['cheie'] == _K_MIN else 'aprobare'
        if r['gama'] == '' and key not in vals:
            vals[key] = float(r['valoare'])
        elif r['gama'] != '':
            vals[key] = float(r['valoare'])
    return {'minima': vals.get('minima', 30.0),
            'aprobare': vals.get('aprobare', 25.0)}


def cond_effective(an, cod_client, furnizor=None, categorie=None, sku=None):
    """Effective conditions % for a client at the given scope.

    Sums all matching pct rows in conditii_comerciale - same additive
    semantics as cond_resolved, extended with the optional categorie/sku
    scopes (NULL in a row = applies to all).
    """
    rows = query("""
        SELECT COALESCE(SUM(CASE WHEN tip_valoare='pct' THEN valoare END), 0) AS pct
        FROM conditii_comerciale
        WHERE an = :an
          AND (cod_client = :cod_client OR cod_client IS NULL)
          AND (furnizor  = :furnizor  OR furnizor  IS NULL)
          AND (categorie = :categorie OR categorie IS NULL)
          AND (sku       = :sku       OR sku       IS NULL)
    """, {"an": an, "cod_client": cod_client, "furnizor": furnizor,
          "categorie": categorie, "sku": sku})
    return rows[0]['pct'] or 0.0
