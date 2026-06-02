"""Tests for pure parsing/utility functions in ETL scripts.

No DB, no I/O — just the transformation logic that is most likely to
break silently when supplier file formats change.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'etl'))

from import_comenzi_tranzit_toras import normalize_ref, parse_order_date, num, s
from import_comenzi_tranzit_celmar import (
    extract_romanian_keyword,
    parse_filename_date,
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
