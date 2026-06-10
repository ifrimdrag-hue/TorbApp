import logging
import sqlite3
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import current_user
from automations.stocuri_shopify.orchestrator import preview, preview_shopify_only, sync
from automations.stocuri_shopify.api_client import ShopifyClient
from paths import DB_PATH

stocuri_shopify_bp = Blueprint('stocuri_shopify', __name__)
logger = logging.getLogger(__name__)


@stocuri_shopify_bp.route('/stocuri/shopify')
def stocuri_shopify_page():
    from flask import redirect, url_for
    return redirect(url_for('stocuri_emag.stocuri_page'))


@stocuri_shopify_bp.route('/api/stocuri/shopify/preview', methods=['POST'])
async def api_shopify_preview():
    try:
        raport = request.files.get('raport')
        if raport:
            result = await preview(raport.read(), raport.filename)
        else:
            result = await preview_shopify_only()
        return jsonify({
            'rows': [r._asdict() for r in result.rows],
            'skus_not_in_shopify': result.skus_not_in_shopify,
            'warnings': result.warnings,
            'summary': result.summary,
            'has_report': result.has_report,
        })
    except Exception as exc:
        logger.exception("Shopify preview failed")
        return jsonify({'error': str(exc)}), 500


@stocuri_shopify_bp.route('/api/stocuri/shopify/sync', methods=['POST'])
async def api_shopify_sync():
    try:
        data = request.get_json(force=True)
        rows_to_update = data.get('rows_to_update', [])
        report_filename = data.get('report_filename', '')
        result = await sync(rows_to_update)

        successful_ids = {
            r['inventory_item_id'] for r in result.results if r.get('ok')
        }
        rows_by_id = {r['inventory_item_id']: r for r in rows_to_update}
        rows_to_save = [rows_by_id[iid] for iid in successful_ids if iid in rows_by_id]

        if rows_to_save:
            with sqlite3.connect(DB_PATH) as c:
                cur = c.execute(
                    "INSERT INTO sync_sessions (sync_at, filename, platform, user_id)"
                    " VALUES (datetime('now','localtime'), ?, 'shopify', ?)",
                    (report_filename, current_user.id),
                )
                session_id = cur.lastrowid
                c.executemany(
                    """INSERT INTO sync_rows
                       (session_id, inventory_item_id, sku, name, old_stock, new_stock, status, platform)
                       VALUES (?, ?, ?, ?, ?, ?, 'updated', 'shopify')""",
                    [
                        (session_id, r['inventory_item_id'], r.get('sku', ''),
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
        logger.exception("Shopify sync failed")
        return jsonify({'error': str(exc)}), 500


@stocuri_shopify_bp.route('/api/stocuri/shopify/connection-test')
async def api_shopify_connection_test():
    try:
        client = ShopifyClient()
        locations = await client.test_connection()
        return jsonify({'ok': True, 'locations': locations})
    except Exception as exc:
        logger.exception("Shopify connection test failed")
        return jsonify({'ok': False, 'error': str(exc)})


@stocuri_shopify_bp.route('/api/stocuri/shopify/sync-history')
def api_shopify_sync_history():
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT s.id, s.sync_at, s.filename, u.username"
                " FROM sync_sessions s"
                " LEFT JOIN users u ON u.id = s.user_id"
                " WHERE s.platform = 'shopify' ORDER BY s.id DESC LIMIT 10"
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
        logger.exception("Shopify sync history fetch failed")
        return jsonify({'error': str(exc)}), 500


@stocuri_shopify_bp.route('/api/stocuri/shopify/sync-history/<int:session_id>')
def api_shopify_sync_history_rows(session_id):
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                """SELECT inventory_item_id, sku, name, old_stock, new_stock, status
                   FROM sync_rows WHERE session_id = ?""",
                (session_id,),
            ).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as exc:
        logger.exception("Shopify sync history rows fetch failed")
        return jsonify({'error': str(exc)}), 500
