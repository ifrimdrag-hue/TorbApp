"""Tests for pure parsing/utility functions in ETL scripts.

No DB, no I/O — just the transformation logic that is most likely to
break silently when supplier file formats change.
"""
import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'etl'))

from import_comenzi_tranzit_toras import normalize_ref, parse_order_date, num, s
from import_comenzi_tranzit_celmar import (
    extract_romanian_keyword,
    parse_filename_date,
    parse_order_sheet,
)


# ── normalize_ref (Toras) ─────────────────────────────────────────────────────

def test_normalize_ref_float_whole():
    assert normalize_ref(569.0) == '569'

def test_normalize_ref_float_decimal():
    # Non-whole floats preserved as-is
    assert normalize_ref(1.5) == '1.5'

def test_normalize_ref_int():
    assert normalize_ref(524) == '524'

def test_normalize_ref_string_leading_zeros():
    # Leading-zero codes like '0401' must not be stripped
    assert normalize_ref('0401') == '0401'

def test_normalize_ref_string_plain():
    assert normalize_ref('569') == '569'

def test_normalize_ref_empty_string_returns_none():
    assert normalize_ref('') is None

def test_normalize_ref_none_returns_none():
    assert normalize_ref(None) is None

def test_normalize_ref_whitespace_returns_none():
    assert normalize_ref('   ') is None


# ── parse_order_date (Toras) ──────────────────────────────────────────────────

def test_parse_order_date_standard():
    assert parse_order_date('ORDER Toras14.04.2026.xls') == '2026-04-14'

def test_parse_order_date_no_date_returns_none():
    assert parse_order_date('ORDER Toras.xls') is None

def test_parse_order_date_different_position():
    assert parse_order_date('Comanda 01.12.2025.xlsx') == '2025-12-01'


# ── num helper (Toras) ────────────────────────────────────────────────────────

def test_num_float_string():
    assert num('3.5') == 3.5

def test_num_int_string():
    assert num('10') == 10.0

def test_num_none_returns_default():
    assert num(None) is None
    assert num(None, 0) == 0

def test_num_empty_returns_default():
    assert num('', 99) == 99

def test_num_non_numeric_returns_default():
    assert num('abc') is None


# ── s helper (Toras) ─────────────────────────────────────────────────────────

def test_s_strips_whitespace():
    assert s('  hello  ') == 'hello'

def test_s_float_whole_number_no_decimal():
    assert s(569.0) == '569'

def test_s_none_returns_none():
    assert s(None) is None

def test_s_empty_string_returns_none():
    assert s('   ') is None


# ── extract_romanian_keyword (Celmar) ─────────────────────────────────────────

def test_extract_keyword_single_word():
    assert extract_romanian_keyword('Chamomile (1.5g x 20)      MUSETEL') == 'MUSETEL'

def test_extract_keyword_compound():
    result = extract_romanian_keyword('Linden with Lemon (1.8 X 20)   TEI CU LAMAIE')
    assert result == 'TEI CU LAMAIE'

def test_extract_keyword_no_romanian_returns_none():
    assert extract_romanian_keyword('Chamomile (1.5g x 20)') is None

def test_extract_keyword_none_input_returns_none():
    assert extract_romanian_keyword(None) is None

def test_extract_keyword_with_diacritics():
    # Romanian diacritics in the keyword
    result = extract_romanian_keyword('Rose hip tea       MACES')
    assert result == 'MACES'


# ── parse_filename_date (Celmar) ──────────────────────────────────────────────

def test_parse_filename_date_standard():
    assert parse_filename_date('ORDER Celmar14.04.2026.xls') == '2026-04-14'

def test_parse_filename_date_no_match():
    assert parse_filename_date('ORDER Celmar.xls') is None


# ── parse_order_sheet (Celmar) ────────────────────────────────────────────────

class _Sheet:
    """Minimal stand-in for an xlrd sheet, built from a list of rows."""

    def __init__(self, rows):
        self._rows = rows
        self.nrows = len(rows)
        self.ncols = max(len(r) for r in rows)

    def cell_value(self, r, c):
        row = self._rows[r]
        return row[c] if c < len(row) else ''


def _order_form(header, *data):
    blank = [''] * len(header)
    return _Sheet([blank, blank, ['ORDER 30/ 12.08.2026'] + blank[1:], blank, blank,
                   header, *data])


def test_celmar_aug_2026_layout_reads_order_pcs_not_value():
    # BUG: the Aug-2026 form dropped a column, so the fixed index 5 of
    # 'Order pcs' became 'TOTAL Value (PLN)' and the value was imported as qty.
    ws = _order_form(
        ['PRODUCT', 'New Price / pcs (PLN)', 'pcs / plallet', ' Order Pallets',
         'Order pcs', 'TOTAL Value (PLN)'],
        ['Chamomile (1.5g x 20)      MUSETEL', 1.1, 3600.0, 10.0, 36000.0, 39600.0],
        ['Rooibos (1.7g x 20)     ROOIBOS', 1.27, 3600.0, '', 0.0, 0.0],
        ['Elder Lemon\xa0(1.5 g x 20)\xa0\xa0SOC CU LAMAIE\xa0\xa0 ', 1.13, 3600.0,
         1.0, 3600.0, 4067.9999999999995],
        ['Mint (1.1 g x 80)\xa0\xa0\xa0MENTA\xa0 ', 2.78, 1080.0, 1.0, 1080.0, 3002.4],
        ['', '', '', 12.0, 40680.0, 46670.4],   # totals row
    )
    lines = parse_order_sheet(ws)
    assert [ln['cantitate_comandata'] for ln in lines] == [36000, 3600, 1080]
    assert [ln['cantitate_baxuri'] for ln in lines] == [10.0, 1.0, 1.0]
    assert [ln['pcs_per_pallet'] for ln in lines] == [3600, 3600, 1080]
    assert lines[0]['pret_valuta'] == 1.1
    assert lines[0]['total_valuta'] == 39600.0
    assert lines[1]['total_valuta'] == 4068.0
    assert extract_romanian_keyword(lines[1]['descriere']) == 'SOC CU LAMAIE'


def test_celmar_legacy_layout_still_parses():
    ws = _order_form(
        ['PRODUCT', 'Price/pcs PLN', 'pcs / pallet', '', 'New order pal', 'Order pcs'],
        ['Linden (1.5g x 20)      TEI', 1.73, 3600.0, '', 2.0, 7200.0],
    )
    [line] = parse_order_sheet(ws)
    assert line['cantitate_comandata'] == 7200
    assert line['cantitate_baxuri'] == 2.0
    assert line['pcs_per_pallet'] == 3600
    assert line['total_valuta'] == 12456.0


def test_celmar_unknown_layout_fails_loudly():
    no_qty = _order_form(['PRODUCT', 'Price / pcs', 'pcs / pallet', 'TOTAL Value'],
                         ['Chamomile (1.5g x 20)      MUSETEL', 1.1, 3600.0, 39600.0])
    with pytest.raises(ValueError, match='Order pcs'):
        parse_order_sheet(no_qty)

    no_header = _Sheet([['ORDER 30'], ['Chamomile      MUSETEL', 1.1]])
    with pytest.raises(ValueError, match='PRODUCT'):
        parse_order_sheet(no_header)

    two_qty = _order_form(['PRODUCT', 'Last order pcs', 'Order pcs'],
                          ['Chamomile (1.5g x 20)      MUSETEL', 3600.0, 36000.0])
    with pytest.raises(ValueError, match='Order pcs'):
        parse_order_sheet(two_qty)
