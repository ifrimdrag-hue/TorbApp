import base64
import logging
from flask import Blueprint, render_template, request, jsonify
from automations.stocuri_shopify.orchestrator import run

stocuri_shopify_bp = Blueprint('stocuri_shopify', __name__)

logger = logging.getLogger(__name__)


@stocuri_shopify_bp.route('/stocuri/shopify')
def stocuri_shopify_page():
    return render_template('stocuri/shopify.html')


@stocuri_shopify_bp.route('/api/stocuri/shopify/run', methods=['POST'])
def api_shopify_run():
    raport = request.files.get('raport')
    inventory = request.files.get('inventory')
    if not raport or not inventory:
        return jsonify({'error': 'Fisierele raport si inventory sunt obligatorii.'}), 400
    try:
        result = run(raport.read(), inventory.read(), raport.filename)
        return jsonify({
            'file_b64': base64.b64encode(result.file_bytes).decode(),
            'filename': 'inventory_updated.csv',
            'summary': result.summary,
            'warnings': result.warnings,
            'skus_no_codmare': result.skus_no_codmare,
            'codmare_not_in_shopify': result.codmare_not_in_shopify,
            'codmare_below_threshold': result.codmare_below_threshold,
        })
    except Exception as exc:
        logger.exception("Shopify run failed")
        return jsonify({'error': str(exc)}), 500
