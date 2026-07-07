import logging
import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from automations.stocuri_emag.api_client import EmagClient
from automations.stocuri_emag.orchestrator import preview, preview_emag_only, sync
from connection_cache import get_status
from paths import DB_PATH

stocuri_emag_bp = Blueprint('stocuri_emag', __name__)

logger = logging.getLogger(__name__)


@stocuri_emag_bp.route('/stocuri')
def stocuri_page():
    return render_template('stocuri/stoc.html')


@stocuri_emag_bp.route('/stocuri/emag')
def stocuri_emag_page():
    return redirect(url_for('stocuri_emag.stocuri_page'))


@stocuri_emag_bp.route('/api/stocuri/emag/preview', methods=['POST'])
async def api_emag_preview():
    try:
        raport = request.files.get('raport')
        if raport:
            result = await preview(raport.read(), raport.filename)
        else:
            result = await preview_emag_only()
        return jsonify({
            'rows': [r._asdict() for r in result.rows],
            'skus_not_in_emag': result.skus_not_in_emag,
            'warnings': result.warnings,
            'summary': result.summary,
            'has_report': result.has_report,
        })
    except Exception as exc:
        logger.exception("eMAG preview failed")
        return jsonify({'error': str(exc)}), 500


@stocuri_emag_bp.route('/api/stocuri/emag/sync', methods=['POST'])
async def api_emag_sync():
    try:
        data = request.get_json(force=True)
        rows_to_update = data.get('rows_to_update', [])
        report_filename = data.get('report_filename', '')
        result = await sync(rows_to_update)

        successful_ids = {r['offer_id'] for r in result.results if r.get('ok')}
        rows_by_id = {r['offer_id']: r for r in rows_to_update}
        rows_to_save = [rows_by_id[oid] for oid in successful_ids if oid in rows_by_id]

        if rows_to_save:
            with sqlite3.connect(DB_PATH) as c:
                cur = c.execute(
                    "INSERT INTO sync_sessions (sync_at, filename, platform, user_id)"
                    " VALUES (datetime('now','localtime'), ?, 'emag', ?)",
                    (report_filename, current_user.id),
                )
                session_id = cur.lastrowid
                c.executemany(
                    """INSERT INTO sync_rows
                       (session_id, inventory_item_id, sku, name, old_stock, new_stock, status, platform)
                       VALUES (?, ?, ?, ?, ?, ?, 'updated', 'emag')""",
                    [
                        (session_id, str(r['offer_id']), r.get('ean', ''),
                         r.get('name', ''), r.get('old_stock'), r['new_stock'])
                        for r in rows_to_save
                    ],
                )

        return jsonify({
            'results': result.results,
            'success_count': result.success_count,
            'error_count': result.error_count,
        })
    except Exception as exc:
        logger.exception("eMAG sync failed")
        return jsonify({'error': str(exc)}), 500


@stocuri_emag_bp.route('/api/stocuri/emag/connection-test')
async def api_emag_connection_test():
    async def _check():
        try:
            client = EmagClient()
            await client.test_connection()
            return {'ok': True}
        except Exception as exc:
            logger.exception("eMAG connection test failed")
            return {'ok': False, 'error': str(exc)}

    return jsonify(await get_status('emag', _check))


@stocuri_emag_bp.route('/api/stocuri/emag/sync-history')
def api_emag_sync_history():
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT s.id, s.sync_at, s.filename, u.username"
                " FROM sync_sessions s"
                " LEFT JOIN adm_users u ON u.id = s.user_id"
                " WHERE s.platform = 'emag' ORDER BY s.id DESC LIMIT 10"
            ).fetchall()
        result = []
        for r in rows:
            try:
                dt = datetime.fromisoformat(r['sync_at'])
                formatted = dt.strftime('%d-%m-%Y %H:%M')
            except Exception:
                formatted = r['sync_at']
            result.append({
                'id': r['id'],
                'sync_at': formatted,
                'filename': r['filename'] or '',
                'username': r['username'] or '',
            })
        return jsonify(result)
    except Exception as exc:
        logger.exception("eMAG sync history fetch failed")
        return jsonify({'error': str(exc)}), 500


@stocuri_emag_bp.route('/api/stocuri/emag/sync-history/<int:session_id>')
def api_emag_sync_history_rows(session_id):
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                """SELECT inventory_item_id AS offer_id, sku AS ean,
                          name, old_stock, new_stock, status
                   FROM sync_rows WHERE session_id = ? AND platform = 'emag'""",
                (session_id,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as exc:
        logger.exception("eMAG sync history rows fetch failed")
        return jsonify({'error': str(exc)}), 500
