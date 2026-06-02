import datetime
import json
import logging
from flask import Blueprint, render_template, request, jsonify, abort
import queries
from ai import ask_question

analytics_bp = Blueprint('analytics', __name__)

logger = logging.getLogger(__name__)

MONTHS_RO = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
             'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _delta_pct(cy, py):
    if not py:
        return None
    return round((cy / py - 1) * 100, 1)


def _build_trend_series(trend_rows):
    """Convert trend query rows to {year: [12 values]} dict."""
    by_year = {}
    for row in trend_rows:
        yr = row['an']
        if yr not in by_year:
            by_year[yr] = [0] * 12
        luna = row['luna']
        if luna:
            by_year[yr][int(luna) - 1] = row['val_neta'] or 0
    return by_year


@analytics_bp.route('/')
def dashboard():
    an = int(request.args.get('an', datetime.date.today().year))

    kpis_raw = queries.kpi_cards()
    kpis = {r['an']: r for r in kpis_raw}
    luna_kpi   = queries.kpi_luna_curenta()
    delta_luna = _delta_pct(luna_kpi['vn_cy'], luna_kpi['vn_py'])
    luna_nume  = MONTHS_RO[luna_kpi['luna_nr'] - 1]
    _kpi_zero = {'val_neta': 0, 'marja_bruta': 0, 'marja_pct': 0, 'marja_neta': 0, 'clienti_activi': 0}
    cy = kpis.get(an, _kpi_zero)
    py = kpis.get(an - 1, _kpi_zero)

    # Deltas
    delta_vn    = _delta_pct(cy.get('val_neta', 0), py.get('val_neta', 0))
    delta_mb    = _delta_pct(cy.get('marja_bruta', 0), py.get('marja_bruta', 0))
    delta_mn    = _delta_pct(cy.get('marja_neta', 0), py.get('marja_neta', 0))
    delta_mpct  = round((cy.get('marja_pct', 0) or 0) - (py.get('marja_pct', 0) or 0), 1)
    delta_clnt  = (cy.get('clienti_activi', 0) or 0) - (py.get('clienti_activi', 0) or 0)

    trend_rows = queries.monthly_trend()
    trend_by_year = _build_trend_series(trend_rows)

    brands      = queries.brand_mix(an)
    channels    = queries.channel_mix(an)
    kaufland_pct = queries.risk_kaufland(an)
    bogdan_pct  = queries.risk_agent(an, 'DRAGNEA BOGDAN')
    churn_list  = queries.churn_clients(60)
    top_10      = queries.top_clients(an)

    return render_template(
        'dashboard.html',
        an=an, luna=None,
        cy=cy, py=py,
        delta_vn=delta_vn, delta_mb=delta_mb, delta_mn=delta_mn,
        delta_mpct=delta_mpct, delta_clnt=delta_clnt,
        trend_json=json.dumps(trend_by_year),
        months_json=json.dumps(MONTHS_RO),
        brands=brands,
        brands_json=json.dumps([{'label': r['furnizor'], 'value': r['val_neta']} for r in brands]),
        channels=channels,
        channels_json=json.dumps([{'label': r['agent'], 'value': r['val_neta']} for r in channels]),
        kaufland_pct=kaufland_pct,
        bogdan_pct=bogdan_pct,
        churn_count=len(churn_list),
        top_10=top_10,
        luna_kpi=luna_kpi,
        delta_luna=delta_luna,
        luna_nume=luna_nume,
    )


@analytics_bp.route('/team')
def team():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)
    max_luna = None if luna else queries.max_luna_for_year(an)
    agents  = queries.team_table(an, luna=luna, max_luna=max_luna)
    py_map  = {r['agent']: r for r in queries.team_table(an - 1, luna=luna, max_luna=max_luna)}
    for row in agents:
        py = py_map.get(row['agent'], {})
        row['val_neta_py'] = py.get('val_neta', 0)
        row['delta_vn'] = _delta_pct(row['val_neta'] or 0, py.get('val_neta', 0))
    return render_template('team.html', an=an, luna=luna, agents=agents, max_luna=max_luna)


@analytics_bp.route('/agent/<path:name>')
def agent_detail(name):
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)
    max_luna = None if luna else queries.max_luna_for_year(an)
    kpi    = queries.agent_kpi(name, an, luna=luna, max_luna=max_luna)
    kpi_py = queries.agent_kpi(name, an - 1, luna=luna, max_luna=max_luna)
    if not kpi:
        abort(404)
    kpi['delta_vn'] = _delta_pct(kpi.get('val_neta', 0), (kpi_py or {}).get('val_neta', 0))
    kpi['max_luna'] = max_luna
    kpi['marja_neta_pct'] = round(
        (kpi.get('marja_neta') or 0) * 100 / (kpi.get('val_neta') or 1), 1
    )

    trend_raw  = queries.agent_monthly_full(name)
    trend_vn   = {}
    trend_mb   = {}
    trend_mn   = {}
    for r in trend_raw:
        yr = r['an']
        idx = int(r['luna']) - 1
        trend_vn.setdefault(yr, [0]*12)[idx] = r['val_neta'] or 0
        trend_mb.setdefault(yr, [0]*12)[idx] = r['marja_bruta'] or 0
        trend_mn.setdefault(yr, [0]*12)[idx] = r['marja_neta'] or 0

    clients = queries.agent_clients_full(name, an, luna=luna, max_luna=max_luna)
    skus    = queries.agent_skus_full(name, an, luna=luna, max_luna=max_luna)
    brands  = queries.agent_brands_full(name, an, luna=luna, max_luna=max_luna)
    monthly_pivot = queries.agent_brand_sku_monthly(name, an)

    return render_template(
        'agent.html',
        agent=name, an=an, luna=luna,
        kpi=kpi, kpi_py=kpi_py,
        trend_vn_json=json.dumps(trend_vn),
        trend_mb_json=json.dumps(trend_mb),
        trend_mn_json=json.dumps(trend_mn),
        months_json=json.dumps(MONTHS_RO),
        clients=clients, skus=skus, brands=brands,
        monthly_pivot=monthly_pivot,
    )


@analytics_bp.route('/clients')
def clients():
    an      = int(request.args.get('an', datetime.date.today().year))
    luna    = request.args.get('luna', type=int)
    search  = request.args.get('q', '').strip()
    agent   = request.args.get('agent', '').strip()
    churn   = request.args.get('churn', '').strip()
    brand   = request.args.get('brand', '').strip()

    max_luna = None if luna else queries.max_luna_for_year(an)
    client_rows = queries.clients_list(
        an,
        search=search or None,
        agent=agent or None,
        churn=churn or None,
        brand=brand or None,
        luna=luna,
        max_luna=max_luna,
    )
    agent_opts = queries.agents_list()
    brand_opts = queries.brands_list()

    return render_template(
        'clients.html',
        an=an, luna=luna, clients=client_rows,
        agent_opts=agent_opts, brand_opts=brand_opts,
        q=search, sel_agent=agent, sel_churn=churn, sel_brand=brand,
    )


@analytics_bp.route('/client/<path:cod_client>')
def client_detail(cod_client):
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)
    info = queries.client_info(cod_client)
    if not info:
        abort(404)
    max_luna = None if luna else queries.max_luna_for_year(an)
    products   = queries.client_products_full(cod_client, an, luna=luna, max_luna=max_luna)
    brand_mix  = queries.client_brand_mix(cod_client, an)
    yearly     = queries.client_yearly_full(cod_client)
    monthly    = queries.client_monthly_full(cod_client)

    monthly_vn = {}
    monthly_mb = {}
    for r in monthly:
        yr  = r['an']
        idx = int(r['luna']) - 1
        monthly_vn.setdefault(yr, [0]*12)[idx] = r['val_neta'] or 0
        monthly_mb.setdefault(yr, [0]*12)[idx] = r['marja_bruta'] or 0

    return render_template(
        'client.html',
        an=an, luna=luna, info=info,
        products=products,
        brand_mix_json=json.dumps([{'label': r['furnizor'], 'value': r['val_neta']} for r in brand_mix]),
        yearly=yearly,
        monthly_vn_json=json.dumps(monthly_vn),
        monthly_mb_json=json.dumps(monthly_mb),
        months_json=json.dumps(MONTHS_RO),
    )


@analytics_bp.route('/products')
def products():
    an      = int(request.args.get('an', datetime.date.today().year))
    luna    = request.args.get('luna', type=int)
    furnizor = request.args.get('brand', '').strip()
    search  = request.args.get('q', '').strip()
    max_luna = None if luna else queries.max_luna_for_year(an)
    brand_rows = queries.products_brands(an, luna=luna, max_luna=max_luna)
    sku_rows   = queries.products_top_skus(an, furnizor=furnizor or None,
                                            search=search or None,
                                            luna=luna, max_luna=max_luna,
                                            limit=200 if search else 50)
    brand_opts = queries.brands_list()
    return render_template(
        'products.html',
        an=an, luna=luna, brand_rows=brand_rows, sku_rows=sku_rows,
        brand_opts=brand_opts, sel_brand=furnizor, sel_search=search,
    )


@analytics_bp.route('/brand/<path:furnizor>')
def brand_detail(furnizor):
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)
    max_luna = None if luna else queries.max_luna_for_year(an)

    kpi    = queries.brand_kpi(furnizor, an, max_luna=max_luna, luna=luna)
    kpi_py = queries.brand_kpi(furnizor, an - 1, max_luna=max_luna, luna=luna)
    if not kpi or not kpi.get('val_neta'):
        abort(404)
    if kpi_py and kpi_py.get('val_neta'):
        kpi['delta_vn'] = _delta_pct(kpi.get('val_neta', 0), kpi_py.get('val_neta', 0))
        kpi['delta_mb'] = round((kpi.get('marja_pct') or 0) - (kpi_py.get('marja_pct') or 0), 1)
        kpi['delta_mn'] = round((kpi.get('marja_neta_pct') or 0) - (kpi_py.get('marja_neta_pct') or 0), 1)
    else:
        kpi['delta_vn'] = None
        kpi['delta_mb'] = None
        kpi['delta_mn'] = None

    monthly_raw = queries.brand_monthly_full(furnizor)
    trend_vn = {}
    trend_mb = {}
    for r in monthly_raw:
        yr = r['an']
        idx = int(r['luna']) - 1
        trend_vn.setdefault(yr, [0]*12)[idx] = r['val_neta'] or 0
        trend_mb.setdefault(yr, [0]*12)[idx] = r['marja_bruta'] or 0

    clients = queries.brand_clients(furnizor, an, max_luna=max_luna, luna=luna)
    search  = request.args.get('q', '').strip()
    skus    = queries.products_top_skus(an, furnizor=furnizor,
                                         limit=300 if search else 30,
                                         search=search or None, luna=luna)

    return render_template(
        'brand.html',
        furnizor=furnizor, an=an, luna=luna, max_luna=max_luna,
        kpi=kpi, kpi_py=kpi_py,
        trend_vn_json=json.dumps(trend_vn),
        trend_mb_json=json.dumps(trend_mb),
        months_json=json.dumps(MONTHS_RO),
        clients=clients, skus=skus, sel_search=search,
    )


@analytics_bp.route('/ask')
def ask():
    return render_template('ask.html')


@analytics_bp.route('/api/ask', methods=['POST'])
def api_ask():
    data = request.get_json(silent=True) or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'error': 'Întrebarea lipsă.'}), 400
    try:
        result = ask_question(question)
        return jsonify(result)
    except Exception as exc:
        logger.exception("api_ask failed")
        return jsonify({'error': str(exc)}), 500
