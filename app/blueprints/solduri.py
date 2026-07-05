import logging
from flask import Blueprint, render_template, request
import queries
from exports.excel_export import send_excel, timestamped_filename

solduri_bp = Blueprint('solduri', __name__)
logger = logging.getLogger(__name__)

_VIEWS = ('client', 'agent', 'invoice')


def _load(view, bucket, agent, search):
    if view == 'agent':
        return queries.solduri_by_agent(bucket=bucket, search=search)
    if view == 'invoice':
        return queries.solduri_by_invoice(bucket=bucket, agent=agent, search=search)
    return queries.solduri_by_client(bucket=bucket, agent=agent, search=search)


def _params():
    view = request.args.get('view', 'client')
    if view not in _VIEWS:
        view = 'client'
    return (
        view,
        request.args.get('bucket') or None,
        request.args.get('agent', '').strip() or None,
        request.args.get('q', '').strip() or None,
    )


@solduri_bp.route('/solduri-neincasate')
def solduri():
    view, bucket, agent, search = _params()
    return render_template(
        'solduri_neincasate.html',
        meta=queries.solduri_meta(),
        kpi=queries.solduri_kpi(),
        rows=_load(view, bucket, agent, search),
        view=view, bucket=bucket, agent=agent, q=search or '',
        agents=queries.solduri_agents(),
    )


@solduri_bp.route('/solduri-neincasate/export/excel')
def solduri_export():
    view, bucket, agent, search = _params()
    rows = _load(view, bucket, agent, search)
    sheet = {'client': 'Solduri Client', 'agent': 'Solduri Agent',
             'invoice': 'Solduri Facturi'}[view]
    return send_excel({sheet: rows}, timestamped_filename(f'solduri_{view}'))
