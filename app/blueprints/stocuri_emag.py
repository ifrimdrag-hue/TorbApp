import logging
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from automations.stocuri_emag.orchestrator import preview, preview_emag_only, sync
from automations.stocuri_emag.api_client import EmagClient

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
        result = await sync(rows_to_update)
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
    try:
        client = EmagClient()
        await client.test_connection()
        return jsonify({'ok': True})
    except Exception as exc:
        logger.exception("eMAG connection test failed")
        return jsonify({'ok': False, 'error': str(exc)})
