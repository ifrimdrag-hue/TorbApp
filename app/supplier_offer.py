"""New-supplier price offer import (pricing module, owner request 2026-07-06).

The owner receives price offers from potential suppliers as xls/xlsx in
arbitrary layouts. Flow: upload -> preview grid -> user maps columns by
letter -> import creates POTENTIAL articles (produse.potential=1) with a
landing cost, ready to be priced in the simulator and put in client offers.
"""
import re
from io import BytesIO

import openpyxl
import xlrd

PREVIEW_ROWS = 15
MAX_COLS = 26  # A..Z is plenty for supplier price lists


def _grid_from_xlsx(data, sheet_index=0):
    wb = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[sheet_index]
    grid = [[cell for cell in row[:MAX_COLS]]
            for row in ws.iter_rows(values_only=True)]
    wb.close()
    return grid


def _grid_from_xls(data, sheet_index=0):
    wb = xlrd.open_workbook(file_contents=data)
    ws = wb.sheet_by_index(sheet_index)
    return [[ws.cell_value(r, c) if c < ws.ncols else None
             for c in range(min(ws.ncols, MAX_COLS))]
            for r in range(ws.nrows)]


def load_grid(filename, data):
    """Full sheet as a list of row-lists (values only)."""
    if filename.lower().endswith('.xlsx'):
        return _grid_from_xlsx(data)
    if filename.lower().endswith('.xls'):
        return _grid_from_xls(data)
    raise ValueError('Format neacceptat - incarca .xls sau .xlsx')


def preview(filename, data):
    grid = load_grid(filename, data)
    return {
        'rows': [[('' if v is None else str(v))[:40] for v in row]
                 for row in grid[:PREVIEW_ROWS]],
        'total_rows': len(grid),
    }


def _col_index(letter):
    letter = (letter or '').strip().upper()
    if not re.fullmatch(r'[A-Z]', letter):
        return None
    return ord(letter) - ord('A')


def _cell(row, idx):
    if idx is None or idx >= len(row):
        return None
    v = row[idx]
    if isinstance(v, str):
        v = v.strip()
    return v if v not in ('', None) else None


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    v = str(v).replace(',', '.')
    v = re.sub(r'[^0-9.\-]', '', v)
    try:
        return float(v)
    except ValueError:
        return None


def parse_rows(filename, data, mapping, start_row):
    """Yield article dicts from the sheet using the letter mapping.

    mapping: {'cod': 'A', 'denumire': 'B', 'pret': 'C', optional 'ean',
    'gramaj', 'buc_bax'}. start_row is 1-based (first data row).
    """
    idx = {k: _col_index(v) for k, v in mapping.items() if v}
    if idx.get('cod') is None or idx.get('denumire') is None \
            or idx.get('pret') is None:
        raise ValueError('Coloanele cod, denumire si pret sunt obligatorii.')
    out = []
    for row in load_grid(filename, data)[max(0, int(start_row) - 1):]:
        cod = _cell(row, idx['cod'])
        denumire = _cell(row, idx['denumire'])
        pret = _num(_cell(row, idx['pret']))
        if cod is None or denumire is None or not pret:
            continue
        if isinstance(cod, float) and cod.is_integer():
            cod = int(cod)
        out.append({
            'cod': str(cod), 'denumire': str(denumire), 'pret': pret,
            'ean': _cell(row, idx.get('ean')),
            'gramaj': _num(_cell(row, idx.get('gramaj'))),
            'buc_bax': _num(_cell(row, idx.get('buc_bax'))),
        })
    return out
