"""Balance (.xls) import for the P&L module. Reads via host xlrd, writes via db.get_db."""
import re
import os
import io
import datetime
import xlrd
import db

_NUMERIC_COLS = ('sid', 'sic', 'sfd', 'sfc', 'rulld', 'rullc', 'rulcd', 'rulcc')


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


def persist_rows(source, entitate, an, luna, rows):
    """Insert parsed rows into pnl_balante_raw + write an 'ok' import_log entry. Returns count."""
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
        conn.executemany("""
            INSERT OR REPLACE INTO pnl_balante_raw
            (source_file,entitate,an,luna,cont,dencont,sid,sic,sfd,sfc,rulld,rullc,rulcd,rulcc)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, records)
        conn.execute("""
            INSERT INTO pnl_import_log(timestamp,source_file,entitate,an,luna,rows,status)
            VALUES(?,?,?,?,?,?,'ok')
        """, (datetime.datetime.now().isoformat(), source, entitate, an, luna, len(records)))
        conn.commit()
        return len(records)
    finally:
        conn.close()


def _log_error(source, entitate, an, luna, error):
    conn = db.get_db()
    try:
        conn.execute("""
            INSERT INTO pnl_import_log(timestamp,source_file,entitate,an,luna,rows,status)
            VALUES(?,?,?,?,?,0,?)
        """, (datetime.datetime.now().isoformat(), source, entitate, an, luna, f'error: {error}'))
        conn.commit()
    finally:
        conn.close()


def import_file(path):
    """Import one .xls. Returns {'ok': bool, 'rows': int, 'error': str|None}."""
    filename = os.path.basename(path)
    entitate = detect_entity(filename)
    try:
        an, luna = parse_period(filename)
    except ValueError as e:
        _log_error(path, entitate, 0, 0, str(e))
        return {'ok': False, 'rows': 0, 'error': str(e)}
    try:
        rows = read_xls_rows(path)
    except Exception as e:
        error_msg = f'xlrd error: {e}'
        _log_error(path, entitate, an, luna, error_msg)
        return {'ok': False, 'rows': 0, 'error': error_msg}
    n = persist_rows(path, entitate, an, luna, rows)
    return {'ok': True, 'rows': n, 'error': None}


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
