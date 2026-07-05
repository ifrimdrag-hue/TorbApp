"""Actualizare Date blueprint: ERP / supplier file imports.

Owns the /actualizare page plus the async upload + import-status APIs. Split
out of forecast.py so the data-import concern lives in one place. Job status is
persisted to the upload_jobs table (migration 0015) so any gunicorn worker can
answer a status poll.
"""
import os
import sys
import threading
import logging
import sqlite3 as _sq
import uuid as _uuid
from flask import Blueprint, render_template, request, jsonify

import db
import paths

logger = logging.getLogger(__name__)

actualizare_bp = Blueprint('actualizare', __name__)

# Global state for import job — tracks status of long-running /api/actualizare-date
_import_job: dict = {'status': 'idle', 'message': ''}
_import_lock = threading.Lock()


@actualizare_bp.route('/actualizare')
def actualizare():
    return render_template('actualizare.html')


def _log_import(tip: str, fisier: str, randuri, durata_s: float, status: str, mesaj: str = ''):
    """Scrie o înregistrare în import_log (conexiune proprie — e apelat din thread)."""
    try:
        conn = _sq.connect(paths.DB_PATH)
        conn.execute(
            "INSERT INTO import_log (tip, fisier, randuri, durata_s, status, mesaj) VALUES (?,?,?,?,?,?)",
            (tip, fisier, randuri, round(durata_s, 2), status, mesaj)
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.warning("_log_import DB write failed for tip=%s fisier=%s", tip, fisier, exc_info=True)


def _job_set(job_id, tip, fisier, status, mesaj=None, randuri=None, avertisment=None):
    """Upsert upload-job state into SQLite (shared across gunicorn workers).

    The former in-memory dict was per-process, so a status poll landing on a
    different worker reported a false "server restarted". DB-backed state lets
    any worker answer, and it survives a real restart.
    """
    try:
        conn = _sq.connect(paths.DB_PATH)
        conn.execute(
            "INSERT INTO upload_jobs "
            "(job_id, tip, fisier, status, mesaj, randuri, avertisment, actualizat_la) "
            "VALUES (?,?,?,?,?,?,?, datetime('now','localtime')) "
            "ON CONFLICT(job_id) DO UPDATE SET "
            "status=excluded.status, mesaj=excluded.mesaj, randuri=excluded.randuri, "
            "avertisment=excluded.avertisment, actualizat_la=excluded.actualizat_la",
            (job_id, tip, fisier, status, mesaj, randuri, avertisment),
        )
        conn.execute("DELETE FROM upload_jobs WHERE creat_la < datetime('now','-2 days')")
        conn.commit()
        conn.close()
    except Exception:
        logger.warning("_job_set DB write failed for job=%s status=%s", job_id, status, exc_info=True)


def _job_get(job_id):
    return db.query_one(
        "SELECT status, mesaj, randuri, avertisment FROM upload_jobs WHERE job_id = :j",
        {"j": job_id},
    )


@actualizare_bp.route('/api/actualizare-date', methods=['POST'])
def api_actualizare_date():
    """Run update_data.py — imports sales + stock and updates gama (async via background thread)."""
    global _import_job
    with _import_lock:
        if _import_job['status'] == 'running':
            return jsonify({'ok': False, 'error': 'Import deja în curs'}), 409
        _import_job = {'status': 'running', 'message': ''}

    def _run():
        global _import_job
        try:
            import subprocess
            proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            result = subprocess.run(
                [sys.executable, 'etl/update_data.py'],
                cwd=proj_root, capture_output=True, text=True, timeout=300,
                encoding='utf-8', errors='replace',
            )
            if result.returncode != 0:
                with _import_lock:
                    _import_job = {'status': 'error', 'message': (result.stderr or result.stdout)[-500:]}
            else:
                with _import_lock:
                    _import_job = {'status': 'done', 'message': 'Import finalizat cu succes'}
        except subprocess.TimeoutExpired:
            logger.error("actualizare-date timed out after 300s")
            with _import_lock:
                _import_job = {'status': 'error', 'message': 'Import timeout (>300s)'}
        except Exception as exc:
            logger.exception("actualizare-date failed")
            with _import_lock:
                _import_job = {'status': 'error', 'message': str(exc)}

    threading.Thread(target=_run, daemon=True, name='import-date').start()
    return jsonify({'ok': True, 'status': 'running'})


@actualizare_bp.route('/api/actualizare-date/status')
def api_actualizare_date_status():
    """Get current status of import job (for polling)."""
    with _import_lock:
        return jsonify(dict(_import_job))


@actualizare_bp.route('/api/import-log')
def api_import_log():
    rows = db.get_db().execute(
        "SELECT id, tip, fisier, randuri, durata_s, status, mesaj, creat_la "
        "FROM import_log ORDER BY id DESC LIMIT 20"
    ).fetchall()
    return jsonify({'ok': True, 'items': [dict(r) for r in rows]})


def _run_upload_job(job_id: str, tip: str, fisier_orig: str, dest_path: str):
    """Rulează importul într-un thread daemon și actualizează starea job-ului în tabela upload_jobs."""
    import time as _time
    import re as _re
    import subprocess as _sub

    script_map = {
        'stoc':             'etl/import_stoc.py',
        'vanzari':          'etl/import_vanzari_erp.py',
        'auchan':           'etl/import_vanzari_tobra_auchan.py',
        'comenzi_basilur':  'etl/import_comenzi_tranzit_basilur.py',
        'comenzi_toras':    'etl/import_comenzi_tranzit_toras.py',
        'comenzi_celmar':   'etl/import_comenzi_tranzit_celmar.py',
        'comenzi_leonex':   'etl/import_comenzi_tranzit_leonex.py',
        'solduri':          'etl/import_solduri_neincasate.py',
    }
    script = script_map[tip]
    proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    t0 = _time.time()

    try:
        import os as _os
        env = {**_os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1'}
        result = _sub.run(
            [sys.executable, script, dest_path],
            cwd=proj_root, capture_output=True, text=True,
            timeout=300, encoding='utf-8', errors='replace',
            env=env,
        )
        durata = _time.time() - t0
        output = (result.stdout or '') + (result.stderr or '')

        # Extrage numărul de rânduri din output
        # import_stoc.py:        "â†’ Stoc importat: 699 rânduri"
        # import_vanzari_erp.py: "â†’ Inserate: 135,420 | Duplicate..."
        randuri = None
        for pattern in [r'([\d,]+)\s*rânduri', r'Inserate:\s*([\d,]+)']:
            m = _re.search(pattern, output)
            if m:
                randuri = int(m.group(1).replace(',', ''))
                break

        if result.returncode != 0:
            logger.error(
                "upload job %s (tip=%s) returncode=%d\nCMD: %s %s\nSTDOUT:\n%s\nSTDERR:\n%s",
                job_id, tip, result.returncode, script, dest_path,
                result.stdout or '(gol)', result.stderr or '(gol)',
            )
            error_detail = output[-500:].strip() or f'Script a ieșit cu codul {result.returncode} (fără output)'
            _log_import(tip, fisier_orig, randuri, durata, 'error', error_detail)
            _job_set(job_id, tip, fisier_orig, 'error', mesaj=error_detail, randuri=randuri)
        else:
            mesaj = f'Import finalizat: {randuri or "?"} rânduri'
            avert = None
            m_av = _re.search(r'^AVERTISMENT:\s*(.+)$', output, _re.MULTILINE)
            if m_av:
                avert = m_av.group(1).strip()
                mesaj += f' | {avert}'
            _log_import(tip, fisier_orig, randuri, durata, 'ok', mesaj)
            _job_set(job_id, tip, fisier_orig, 'done', mesaj=mesaj, randuri=randuri, avertisment=avert)
    except _sub.TimeoutExpired:
        durata = _time.time() - t0
        logger.error("upload job %s timed out after 300s (tip=%s)", job_id, tip)
        _log_import(tip, fisier_orig, None, durata, 'error', 'Timeout >300s')
        _job_set(job_id, tip, fisier_orig, 'error', mesaj='Timeout import (>300s)')
    except Exception as exc:
        durata = _time.time() - t0
        logger.exception("upload job %s failed (tip=%s)", job_id, tip)
        _log_import(tip, fisier_orig, None, durata, 'error', str(exc))
        _job_set(job_id, tip, fisier_orig, 'error', mesaj=str(exc))


@actualizare_bp.route('/api/upload/<tip>', methods=['POST'])
def api_upload(tip):
    if tip not in ('stoc', 'vanzari', 'auchan', 'comenzi_basilur', 'comenzi_toras', 'comenzi_celmar', 'comenzi_leonex', 'solduri'):
        return jsonify({'ok': False, 'error': 'Tip necunoscut'}), 400

    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'Niciun fișier'}), 400

    try:
        from werkzeug.utils import secure_filename as _secure_filename
        fisier_orig = _secure_filename(f.filename) or f.filename
        proj_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        dest_dir = os.path.join(proj_root, 'docs_input', 'rapoarte')
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, fisier_orig)
        f.save(dest_path)
    except Exception as exc:
        logger.exception("api_upload: eroare salvare fisier tip=%s", tip)
        return jsonify({'ok': False, 'error': f'Eroare server: {exc}'}), 500

    job_id = str(_uuid.uuid4())
    _job_set(job_id, tip, fisier_orig, 'running')

    threading.Thread(
        target=_run_upload_job,
        args=(job_id, tip, fisier_orig, dest_path),
        daemon=True,
        name=f'upload-{tip}',
    ).start()

    return jsonify({'ok': True, 'job_id': job_id})


@actualizare_bp.route('/api/upload/status/<job_id>')
def api_upload_status(job_id):
    job = _job_get(job_id)
    if job is None:
        return jsonify({
            'ok': True,
            'status': 'error',
            'mesaj': 'Job de import negăsit în baza de date. Serverul a fost probabil repornit — verificați Istoric importuri recente sau reimportați fișierul.',
            'randuri': None,
        })
    return jsonify({'ok': True, **job})
