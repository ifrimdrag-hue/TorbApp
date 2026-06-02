import logging
from datetime import datetime
from io import BytesIO
from flask import Blueprint, render_template, request, jsonify, abort, send_file
from automations.campanii.models import Campaign, Task
from automations.campanii import storage as campanii_storage
from automations.campanii.stock_validator import validate as validate_campaign_stock
from automations.campanii.price_calculator import calculate_prices, estimate_reach

campanii_bp = Blueprint('campanii', __name__)

logger = logging.getLogger(__name__)


@campanii_bp.route('/campanii')
def campanii_page():
    return render_template('campanii/index.html')


@campanii_bp.route('/api/campanii')
def api_campanii_list():
    return jsonify([c.model_dump(mode='json') for c in campanii_storage.load_all()])


@campanii_bp.route('/api/campanii', methods=['POST'])
def api_campanii_create():
    try:
        c = Campaign.model_validate(request.get_json(force=True))
        saved = campanii_storage.upsert(c)
        return jsonify(saved.model_dump(mode='json'))
    except Exception as exc:
        logger.exception("campanii create failed")
        return jsonify({'error': str(exc)}), 400


@campanii_bp.route('/api/campanii/<cid>', methods=['PUT'])
def api_campanii_update(cid):
    if not campanii_storage.get(cid):
        abort(404)
    try:
        c = Campaign.model_validate(request.get_json(force=True))
        c.id = cid
        saved = campanii_storage.upsert(c)
        return jsonify(saved.model_dump(mode='json'))
    except Exception as exc:
        logger.exception("campanii update failed")
        return jsonify({'error': str(exc)}), 400


@campanii_bp.route('/api/campanii/<cid>', methods=['DELETE'])
def api_campanii_delete(cid):
    ok = campanii_storage.delete(cid)
    if not ok:
        abort(404)
    return jsonify({'ok': True})


@campanii_bp.route('/api/campanii/<cid>/validate-stock', methods=['POST'])
def api_campanii_validate_stock(cid):
    c = campanii_storage.get(cid)
    if not c:
        abort(404)
    return jsonify(validate_campaign_stock(c))


@campanii_bp.route('/api/campanii/<cid>/calculate-prices', methods=['POST'])
def api_campanii_calculate_prices(cid):
    c = campanii_storage.get(cid)
    if not c:
        abort(404)
    return jsonify(calculate_prices(c))


@campanii_bp.route('/api/campanii/<cid>/estimate-reach', methods=['POST'])
def api_campanii_estimate_reach(cid):
    c = campanii_storage.get(cid)
    if not c:
        abort(404)
    return jsonify(estimate_reach(c))


@campanii_bp.route('/api/campanii/<cid>/ai-generate', methods=['POST'])
def api_campanii_ai_generate(cid):
    from automations.ai.claude_client import generate_campaign_content
    c = campanii_storage.get(cid)
    if not c:
        abort(404)
    photo = request.files.get('photo')
    notes = request.form.get('notes', '')
    image_bytes = None
    image_media_type = 'image/jpeg'
    if photo and photo.filename:
        fname = photo.filename.lower()
        if fname.endswith(('.jpg', '.jpeg')):
            image_media_type = 'image/jpeg'
        elif fname.endswith('.png'):
            image_media_type = 'image/png'
        elif fname.endswith('.webp'):
            image_media_type = 'image/webp'
        image_bytes = photo.read()
        if len(image_bytes) > 10 * 1024 * 1024:
            return jsonify({'ok': False, 'error': 'Poza prea mare (max 10 MB).'}), 400
    return jsonify(generate_campaign_content(
        campaign=c.model_dump(mode='json'),
        image_bytes=image_bytes,
        image_media_type=image_media_type,
        extra_notes=notes,
    ))


@campanii_bp.route('/api/campanii/ai-generate-proposals', methods=['POST'])
def api_campanii_ai_proposals():
    from automations.ai.campaign_generator import generate_campaign_proposals
    payload = request.get_json(force=True) or {}
    period_start = (payload.get('period_start') or '').strip()
    period_end = (payload.get('period_end') or '').strip()
    if not period_start or not period_end:
        return jsonify({'error': 'Perioada (period_start, period_end) e obligatorie.'}), 400
    try:
        total_budget = float(payload.get('total_budget') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'Buget total invalid.'}), 400
    return jsonify(generate_campaign_proposals(
        period_start=period_start,
        period_end=period_end,
        total_budget=total_budget,
        num_campaigns=int(payload.get('num_campaigns') or 3),
        goal=(payload.get('goal') or '').strip(),
        brands_focus=payload.get('brands_focus') or None,
        notes=payload.get('notes') or '',
    ))


@campanii_bp.route('/api/campanii/ai-save-selected', methods=['POST'])
def api_campanii_ai_save_selected():
    proposals = (request.get_json(force=True) or {}).get('proposals') or []
    if not proposals:
        return jsonify({'error': 'Nicio propunere selectata.'}), 400
    created = []
    for prop in proposals:
        try:
            campaign = Campaign(
                name=prop.get('name', ''),
                type=prop.get('type', 'promo'),
                mechanic=prop.get('mechanic', ''),
                date_start=prop.get('date_start'),
                date_end=prop.get('date_end'),
                channels=prop.get('channels', []),
                discount=prop.get('discount') or {'type': 'none', 'value': None},
                budget_alloc=prop.get('budget_alloc'),
                products=prop.get('products', []),
                status='draft',
                notes=(prop.get('notes', '') + (
                    '\n\nStrategy: ' + prop['strategy_rationale']
                    if prop.get('strategy_rationale') else ''
                )).strip(),
            )
            saved = campanii_storage.upsert(campaign)
            for t in prop.get('tasks', []):
                try:
                    saved.tasks.append(Task(
                        title=t.get('title', ''),
                        priority=t.get('priority', 'medium'),
                        deadline=t.get('deadline'),
                        assignee=t.get('assignee', ''),
                        assignee_type=t.get('assignee_type', 'internal'),
                    ))
                except Exception:
                    pass
            campanii_storage.upsert(saved)
            created.append({'id': saved.id, 'name': saved.name})
        except Exception:
            continue
    return jsonify({'ok': True, 'created': created, 'count': len(created)})


@campanii_bp.route('/api/campanii/<cid>/tasks', methods=['POST'])
def api_task_create(cid):
    c = campanii_storage.get(cid)
    if not c:
        abort(404)
    try:
        task = Task.model_validate(request.get_json(force=True))
        c.tasks.append(task)
        campanii_storage.upsert(c)
        return jsonify(task.model_dump(mode='json'))
    except Exception as exc:
        return jsonify({'error': str(exc)}), 400


@campanii_bp.route('/api/campanii/<cid>/tasks/<tid>', methods=['PUT'])
def api_task_update(cid, tid):
    c = campanii_storage.get(cid)
    if not c:
        abort(404)
    for i, t in enumerate(c.tasks):
        if t.id == tid:
            try:
                task = Task.model_validate(request.get_json(force=True))
                task.id = tid
                task.created_at = t.created_at
                task.updated_at = datetime.now()
                if task.status == 'done' and t.status != 'done':
                    task.completed_at = datetime.now()
                elif task.status != 'done':
                    task.completed_at = None
                c.tasks[i] = task
                campanii_storage.upsert(c)
                return jsonify(task.model_dump(mode='json'))
            except Exception as exc:
                return jsonify({'error': str(exc)}), 400
    abort(404)


@campanii_bp.route('/api/campanii/<cid>/tasks/<tid>', methods=['DELETE'])
def api_task_delete(cid, tid):
    c = campanii_storage.get(cid)
    if not c:
        abort(404)
    before = len(c.tasks)
    c.tasks = [t for t in c.tasks if t.id != tid]
    if len(c.tasks) == before:
        abort(404)
    campanii_storage.upsert(c)
    return jsonify({'ok': True})


@campanii_bp.route('/api/exports/sedinta', methods=['POST'])
def api_export_sedinta():
    from automations.exports.orchestrator import build_export_bundle
    campaigns = [c.model_dump(mode='json') for c in campanii_storage.load_all()]
    if not campaigns:
        return jsonify({'ok': False, 'error': 'Nu exista campanii. Adauga macar una inainte de export.'}), 400
    try:
        bundle = build_export_bundle(campaigns)
    except Exception:
        logger.exception('export sedinta failed')
        return jsonify({'ok': False, 'error': 'Eroare la generarea pachetului de export.'}), 500
    buf = BytesIO(bundle.zip_bytes)
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name=bundle.zip_filename)
