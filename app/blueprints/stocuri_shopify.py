import logging
from flask import Blueprint, request, jsonify
from automations.stocuri_shopify.orchestrator import preview, preview_shopify_only, sync
from automations.stocuri_shopify.api_client import ShopifyClient

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
        result = await sync(rows_to_update)
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
