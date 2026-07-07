import logging
from flask import Blueprint, abort, render_template, request
import queries
from exports.excel_export import send_excel, timestamped_filename

solduri_bp = Blueprint('solduri', __name__)
logger = logging.getLogger(__name__)

_VIEWS = ('client', 'agent', 'invoice')


def _load(view, bucket, agent, search, codcli=None):
    if view == 'agent':
        return queries.solduri_by_agent(bucket=bucket, search=search)
    if view == 'invoice':
        return queries.solduri_by_invoice(bucket=bucket, agent=agent,
                                          search=search, codcli=codcli)
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
        request.args.get('codcli', '').strip() or None,
    )


@solduri_bp.route('/solduri-neincasate')
def solduri():
    view, bucket, agent, search, _ = _params()
    return render_template(
        'solduri_neincasate.html',
        meta=queries.solduri_meta(),
        kpi=queries.solduri_kpi(agent=agent, search=search),
        rows=_load(view, bucket, agent, search),
        view=view, bucket=bucket, agent=agent, q=search or '',
    )


@solduri_bp.route('/solduri-neincasate/client/<path:codcli>')
def solduri_client(codcli):
    header = queries.solduri_client_header(codcli)
    if not header or not header['nr_documente']:
        abort(404)
    return render_template(
        'solduri_client.html',
        header=header,
        rows=queries.solduri_by_invoice(codcli=codcli),
        has_fisa=bool(queries.client_info(codcli)),
    )


@solduri_bp.route('/solduri-neincasate/export/excel')
def solduri_export():
    view, bucket, agent, search, codcli = _params()
    rows = _load(view, bucket, agent, search, codcli=codcli)
    sheet = {'client': 'Solduri Client', 'agent': 'Solduri Agent',
             'invoice': 'Solduri Facturi'}[view]
    return send_excel({sheet: rows}, timestamped_filename(f'solduri_{view}'))
