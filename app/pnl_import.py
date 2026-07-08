"""Balance (.xls) import for the P&L module. Reads via host xlrd, writes via db.get_db.

F0 semantics: an import of (entitate, an, luna) fully replaces any previous rows
for that period in a single transaction, so a corrected balance leaves no ghost
accounts behind. Every import also computes three validations (echilibru,
inlantuire with the prior month, reconciliere with account 121) and stores them
as JSON on the import-log row; imports always succeed, warnings are surfaced in
the UI.
"""
import re
import os
import io
import json
import datetime
import xlrd
import db

_NUMERIC_COLS = ('sid', 'sic', 'sfd', 'sfc', 'rulld', 'rullc', 'rulcd', 'rulcc')
_TOL = 0.05


def detect_entity(filename):
    """'tobra' takes precedence; default 'torb'."""
    name = filename.lower()
    if 'tobra' in name:
        return 'tobra'
    if 'torb' in name:
        return 'torb'
    return 'torb'


def parse_period(filename):
    """(year, month) from filename, e.g. '01 2025.xls', 'bal 05 2025 tobra.xls'."""
    nums = re.findall(r'\d+', os.path.basename(filename))
    candidates = [(int(n), int(m)) for n, m in zip(nums, nums[1:]) if len(m) == 4]
    if candidates:
        month, year = candidates[0]
        if not (1 <= month <= 12):
            raise ValueError(f"Invalid month {month} in filename: {filename}")
        return year, month
    raise ValueError(f"Cannot parse period from filename: {filename}")


def read_xls_rows(path):
    """All rows from a .xls balance file as list of dicts (host xlrd pattern)."""
    wb = xlrd.open_workbook(path, logfile=io.StringIO())
    ws = wb.sheet_by_index(0)
    if ws.nrows < 2:
        return []
    header = [str(ws.cell_value(0, c)).strip().lower() for c in range(ws.ncols)]
    rows = []
    for i in range(1, ws.nrows):
        row = {col: ws.cell_value(i, j) for j, col in enumerate(header)}
        if row.get('cont'):
            row['cont'] = str(row['cont']).strip().split('.')[0]
            rows.append(row)
    return rows


def _num(row, key):
    return float(row.get(key, 0) or 0)


def _validate_echilibru(rows):
    """Trial balance must balance: Σdebit == Σcredit for opening, closing, turnover."""
    def diff(a, b):
        return round(sum(_num(r, a) for r in rows) - sum(_num(r, b) for r in rows), 2)
    d_sold_init = diff('sid', 'sic')
    d_sold_fin = diff('sfd', 'sfc')
    d_rulaj = diff('rulcd', 'rulcc')
    ok = all(abs(x) < _TOL for x in (d_sold_init, d_sold_fin, d_rulaj))
    return {'ok': ok, 'sold_initial': d_sold_init,
            'sold_final': d_sold_fin, 'rulaj': d_rulaj}


def _validate_inlantuire(conn, entitate, an, luna, rows):
    """Month-to-month chaining check. In these balances sid/sic is the *year*
    opening (constant across months), so chaining is verified on the cumulative
    turnover: the increase in rulcd/rulcc from the prior month must equal this
    month's own rulld/rullc. A mismatch is the fingerprint of a prior-period
    correction applied after later months were already imported — those later
    months must be re-imported. Cumulative turnover resets each January, so the
    year boundary (luna == 1) is not chained."""
    if luna <= 1:
        return {'ok': True, 'prior_present': False, 'mismatches': 0, 'max_diff': 0.0}
    prior = {r['cont']: r for r in conn.execute(
        "SELECT cont, rulcd, rulcc FROM pnl_balante_raw WHERE entitate=? AND an=? AND luna=?",
        (entitate, an, luna - 1))}
    if not prior:
        return {'ok': True, 'prior_present': False, 'mismatches': 0, 'max_diff': 0.0}
    mismatches = 0
    max_diff = 0.0
    for r in rows:
        p = prior.get(r['cont'])
        if p is None:
            continue
        d = max(abs(_num(r, 'rulcd') - (p['rulcd'] or 0) - _num(r, 'rulld')),
                abs(_num(r, 'rulcc') - (p['rulcc'] or 0) - _num(r, 'rullc')))
        if d >= _TOL:
            mismatches += 1
            max_diff = max(max_diff, d)
    return {'ok': mismatches == 0, 'prior_present': True,
            'mismatches': mismatches, 'max_diff': round(max_diff, 2)}


def _validate_reconciliere_121(conn, rows):
    """Computed net-profit YTD (cumulative rulcd × mapping semn) must equal the
    account-121 balance (sfc − sfd) carried in the same file."""
    mapping = {r[0]: int(r[1]) for r in conn.execute(
        "SELECT cont, semn FROM pnl_mapping_conturi")}
    pn_ytd = sum(mapping[r['cont']] * _num(r, 'rulcd')
                 for r in rows if r['cont'] in mapping)
    sold_121 = next(((_num(r, 'sfc') - _num(r, 'sfd'))
                     for r in rows if r['cont'] == '121'), None)
    if sold_121 is None:
        return {'ok': False, 'pn_ytd': round(pn_ytd, 2),
                'sold_121': None, 'diff': None}
    diff = round(pn_ytd - sold_121, 2)
    return {'ok': abs(diff) < _TOL, 'pn_ytd': round(pn_ytd, 2),
            'sold_121': round(sold_121, 2), 'diff': diff}


def compute_validations(conn, entitate, an, luna, rows):
    """Run the three import validations against an open connection (rows already
    inserted for the current period, so prior periods are queryable)."""
    return {
        'echilibru': _validate_echilibru(rows),
        'inlantuire': _validate_inlantuire(conn, entitate, an, luna, rows),
        'reconciliere_121': _validate_reconciliere_121(conn, rows),
    }


def persist_rows(source, entitate, an, luna, rows):
    """Full-replace (entitate, an, luna) then insert + log. Returns result dict."""
    conn = db.get_db()
    try:
        records = []
        for r in rows:
            cont = str(r.get('cont', '') or '')
            if not cont:
                continue
            records.append((
                source, entitate, an, luna, cont, str(r.get('dencont', '')),
                *(float(r.get(c, 0) or 0) for c in _NUMERIC_COLS),
            ))
        cur = conn.execute(
            "DELETE FROM pnl_balante_raw WHERE entitate=? AND an=? AND luna=?",
            (entitate, an, luna))
        replaced = cur.rowcount
        conn.executemany("""
            INSERT INTO pnl_balante_raw
            (source_file,entitate,an,luna,cont,dencont,sid,sic,sfd,sfc,rulld,rullc,rulcd,rulcc)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, records)
        validari = compute_validations(conn, entitate, an, luna, rows)
        conn.execute("""
            INSERT INTO pnl_import_log(timestamp,source_file,entitate,an,luna,rows,replaced,status,validari)
            VALUES(?,?,?,?,?,?,?,'ok',?)
        """, (datetime.datetime.now().isoformat(), source, entitate, an, luna,
              len(records), replaced, json.dumps(validari)))
        conn.commit()
        return {'rows': len(records), 'replaced': replaced, 'validari': validari}
    finally:
        conn.close()


def _log_error(source, entitate, an, luna, error):
    conn = db.get_db()
    try:
        conn.execute("""
            INSERT INTO pnl_import_log(timestamp,source_file,entitate,an,luna,rows,replaced,status)
            VALUES(?,?,?,?,?,0,0,?)
        """, (datetime.datetime.now().isoformat(), source, entitate, an, luna, f'error: {error}'))
        conn.commit()
    finally:
        conn.close()


def import_file(path):
    """Import one .xls. Returns {'ok', 'rows', 'replaced', 'validari', 'error'}."""
    filename = os.path.basename(path)
    entitate = detect_entity(filename)
    try:
        an, luna = parse_period(filename)
    except ValueError as e:
        _log_error(path, entitate, 0, 0, str(e))
        return {'ok': False, 'rows': 0, 'replaced': 0, 'validari': None, 'error': str(e)}
    try:
        rows = read_xls_rows(path)
    except Exception as e:
        error_msg = f'xlrd error: {e}'
        _log_error(path, entitate, an, luna, error_msg)
        return {'ok': False, 'rows': 0, 'replaced': 0, 'validari': None, 'error': error_msg}
    res = persist_rows(path, entitate, an, luna, rows)
    return {'ok': True, 'rows': res['rows'], 'replaced': res['replaced'],
            'validari': res['validari'], 'error': None}


def scan_folders():
    """Import .xls files in configured folders not already imported. Returns list of results."""
    from config import settings
    imported = {r['source_file'] for r in db.query(
        "SELECT source_file FROM pnl_import_log WHERE status='ok'")}
    results = []
    for folder in (settings.pnl_torb_folder, settings.pnl_tobra_folder):
        if not folder or not os.path.isdir(folder):
            continue
        for fname in os.listdir(folder):
            if not fname.lower().endswith('.xls'):
                continue
            full = os.path.join(folder, fname)
            if full in imported:
                continue
            result = import_file(full)
            result['filename'] = fname
            results.append(result)
    return results
