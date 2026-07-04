"""Unit tests for the transaction-SKU -> catalog-key resolver (queries._shared).

Supplier catalogs use mixed key formats; the resolver powers the
produse-nelistate exclusion on the client page (bug fix 2026-07-04:
the old plain NOT IN join excluded nothing, so the section listed the
entire catalog regardless of what the client already buys).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from queries._shared import resolve_catalog_sku  # noqa: E402

CATALOG = {'70197-00', '71618-00', '040', 'INTENSE MASK 705839',
           'CELMAR MENTA X'}
EAN = {'5947226224191': '040'}
COD_MARE = {'B.CEAI SPECIAL (2GX20) 71999-4792252999999': '71618-00'}


def _r(sku):
    return resolve_catalog_sku(sku, CATALOG, EAN, COD_MARE)


def test_verbatim_match():
    assert _r('INTENSE MASK 705839') == 'INTENSE MASK 705839'


def test_code_ean_tail_maps_to_dash00():
    assert _r('B.CEAI BOUQUET ASSORTED (1.5GX25) 70197-4792252001121') == '70197-00'


def test_cod_mare_map_priority_over_code_tail():
    # cod_mare says 71618-00 even though the embedded code is 71999
    assert _r('B.CEAI SPECIAL (2GX20) 71999-4792252999999') == '71618-00'


def test_trailing_ean_lookup():
    assert _r('CELMAR AFINE 5947226224191') == '040'


def test_parenthesized_ean_lookup():
    assert _r('CELMAR AFINE (5947226224191)') == '040'


def test_unresolvable_returns_none():
    assert _r('PRODUS NECUNOSCUT 123') is None
    assert _r('') is None
    assert _r(None) is None
