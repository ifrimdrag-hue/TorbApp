import os
import datetime
import tempfile
from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import db
import queries
import pnl_logic
import pnl_import
from exports.excel_export import timestamped_filename, build_pnl_xlsx

pnl_bp = Blueprint('pnl', __name__)

MONTHS_RO = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
             'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
ENTITATI = [('torb', 'Torb Logistic'), ('tobra', 'Tobra Invest'), ('grup', 'Grup consolidat')]


@pnl_bp.app_template_filter('pnl_num')
def _fmt_pnl_num(v):
    """Plain thousands-formatted RON amount (no suffix) for the dense P&L grid."""
    if v is None:
        return '—'
    try:
        f = float(v)
        if abs(f) >= 1_000_000:
            return f"{f / 1_000_000:.2f}M"
        return f"{int(f):,}".replace(',', '.')
    except (TypeError, ValueError):
        return str(v)


def _severity_class(sev):
    return {'error': 'table-danger', 'warning': 'table-warning',
            'success': 'table-success', 'ok': '', None: ''}.get(sev, '')


@pnl_bp.route('/pnl')
def pnl():
    years = pnl_logic.available_years()
    cy = int(request.args.get('an', datetime.date.today().year))
    py = cy - 1
    entitate = request.args.get('entitate', 'torb')
    show_pct = request.args.get('pct', '0') == '1'

    data_cy = pnl_logic.compute_pnl_year(entitate, cy)
    data_py = pnl_logic.compute_pnl_year(entitate, py)
    luni_cy = sorted(data_cy.keys())
    luni_py = queries.pnl_available_months(py, entitate)

    max_luna_cy = max(luni_cy) if luni_cy else 0
    ytd_cy = pnl_logic.compute_ytd(entitate, cy, max_luna_cy) if max_luna_cy else {}
    ytd_py = pnl_logic.compute_ytd(entitate, py, max_luna_cy) if luni_py else {}

    alarm_config = pnl_logic.load_alarm_config()
    alarms = {}
    for luna in luni_cy:
        for _, _label, key in pnl_logic.PNL_STRUCTURE:
            cy_val = data_cy.get(luna, {}).get(key)
            py_val = data_py.get(luna, {}).get(key)
            cfg = alarm_config.get(key, {})
            pct_val = cy_val if key.endswith('%') else None
            a = pnl_logic.compute_alarm(cy_val, py_val, pct_val, cfg)
            trend = pnl_logic.compute_trend_alarm(
                entitate, key, cy, luna, int(cfg.get('alarma_trend_luni', 3) or 3))
            alarms[(luna, key)] = {**a, 'trend': trend}

    return render_template(
        'pnl/pnl.html',
        years=years, cy=cy, py=py, entitate=entitate, entitati=ENTITATI,
        luni_cy=luni_cy, months_ro=MONTHS_RO, structure=pnl_logic.PNL_STRUCTURE,
        data_cy=data_cy, data_py=data_py, ytd_cy=ytd_cy, ytd_py=ytd_py,
        alarms=alarms, show_pct=show_pct, severity_class=_severity_class)


@pnl_bp.route('/pnl/import')
def import_page():
    return render_template('pnl/import.html', logs=queries.pnl_import_log(50))


@pnl_bp.route('/pnl/api/scan', methods=['POST'])
def api_scan():
    return jsonify({'ok': True, 'results': pnl_import.scan_folders()})


@pnl_bp.route('/pnl/api/upload', methods=['POST'])
def api_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'Fișier lipsă'}), 400
    f = request.files['file']
    if not f.filename.lower().endswith('.xls'):
        return jsonify({'error': 'Doar fișiere .xls sunt acceptate'}), 400
    safe_name = secure_filename(f.filename) or 'upload.xls'
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, safe_name)
    f.save(tmp_path)
    try:
        result = pnl_import.import_file(tmp_path)
        result['filename'] = f.filename
    except Exception as e:
        result = {'ok': False, 'rows': 0, 'error': str(e)}
    finally:
        os.unlink(tmp_path)
        os.rmdir(tmp_dir)
    return jsonify(result)


@pnl_bp.route('/pnl/alarm-config')
def alarm_config():
    return render_template('pnl/alarm_config.html', rows=queries.pnl_config_rows())


@pnl_bp.route('/pnl/api/alarm-config', methods=['POST'])
def api_alarm_config_save():
    data = request.get_json(silent=True) or {}
    conn = db.get_db()
    try:
        for row in data.get('rows', []):
            def _f(val):
                return float(val) if val not in (None, '') else None
            conn.execute("""
                INSERT OR REPLACE INTO pnl_config
                (pnl_line, alarma_delta_warn, alarma_delta_err,
                 alarma_prag_warn, alarma_prag_err, alarma_trend_luni, directie)
                VALUES(?,?,?,?,?,?,?)
            """, (
                row.get('pnl_line', ''),
                _f(row.get('delta_warn')), _f(row.get('delta_err')),
                _f(row.get('prag_warn')), _f(row.get('prag_err')),
                int(row.get('trend_luni') or 3),
                row.get('directie', 'sus_bine'),
            ))
        conn.commit()
    finally:
        conn.close()
    return jsonify({'ok': True})


@pnl_bp.route('/pnl/export')
def export_pnl():
    an = int(request.args.get('an', datetime.date.today().year))
    buf = build_pnl_xlsx(an)
    return send_file(
        buf, as_attachment=True, download_name=timestamped_filename(f'pnl_{an}'),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
