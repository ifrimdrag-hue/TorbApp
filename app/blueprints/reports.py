import datetime
import json
import logging
from flask import Blueprint, render_template, request, abort, send_file
import queries
from exports import ppt_export
from exports.excel_export import send_excel, timestamped_filename

reports_bp = Blueprint('reports', __name__)

logger = logging.getLogger(__name__)

MONTHS_RO = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
             'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def _delta_pct(cy, py):
    if not py:
        return None
    return round((cy / py - 1) * 100, 1)


def _build_trend_series(trend_rows):
    by_year = {}
    for row in trend_rows:
        yr = row['an']
        if yr not in by_year:
            by_year[yr] = [0] * 12
        luna = row['luna']
        if luna:
            by_year[yr][int(luna) - 1] = row['val_neta'] or 0
    return by_year



# ---------------------------------------------------------------------------
# Produs (SKU) detaliu
# ---------------------------------------------------------------------------

@reports_bp.route('/produs/<path:sku>')
def produs_detail(sku):
    an      = int(request.args.get('an', datetime.date.today().year))
    luna    = request.args.get('luna', type=int)
    max_luna = None if luna else queries.max_luna_for_year(an)
    kpi     = queries.product_kpi(sku, an, luna=luna, max_luna=max_luna)
    kpi_py  = queries.product_kpi(sku, an - 1, luna=luna, max_luna=max_luna)
    if not kpi:
        abort(404)
    kpi['delta_vn'] = _delta_pct(kpi.get('val_neta', 0), (kpi_py or {}).get('val_neta', 0))

    clients = queries.product_clients(sku, an, luna=luna, max_luna=max_luna)
    clients_istoric, istoric_years = queries.product_clients_istoric(sku)
    monthly = queries.product_monthly(sku)
    yearly  = queries.product_yearly(sku)

    trend = {}
    for r in monthly:
        yr  = r['an']
        idx = int(r['luna']) - 1
        trend.setdefault(yr, [0]*12)[idx] = r['val_neta'] or 0

    return render_template(
        'produs.html',
        sku=sku, an=an, luna=luna,
        kpi=kpi, kpi_py=kpi_py,
        clients=clients, yearly=yearly,
        clients_istoric=clients_istoric, istoric_years=istoric_years,
        trend_json=json.dumps(trend),
        months_json=json.dumps(MONTHS_RO),
    )


# ---------------------------------------------------------------------------
# Profitabilitate — matrice și ranking
# ---------------------------------------------------------------------------

@reports_bp.route('/profitabilitate')
def profitabilitate():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)
    tab  = request.args.get('tab', 'agenti')
    max_luna = None if luna else queries.max_luna_for_year(an)

    agents   = queries.profitabilitate_agenti(an, max_luna=max_luna, luna=luna)
    clients  = queries.profitabilitate_clienti(an, max_luna=max_luna, luna=luna)
    products = queries.profitabilitate_produse(an, max_luna=max_luna, luna=luna)
    matrice_rows = queries.profitabilitate_matrice(an, max_luna=max_luna, luna=luna)

    # Build matrix structure: {agent: {furnizor: marja_neta_pct}}
    agents_in_matrix = sorted({r['agent'] for r in matrice_rows})
    brands_in_matrix = sorted({r['furnizor'] for r in matrice_rows})
    matrice = {a: {} for a in agents_in_matrix}
    for r in matrice_rows:
        matrice[r['agent']][r['furnizor']] = r['marja_neta_pct']

    return render_template(
        'profitabilitate.html',
        an=an, luna=luna, tab=tab,
        agents=agents, clients=clients, products=products,
        matrice=matrice,
        matrice_agents=agents_in_matrix,
        matrice_brands=brands_in_matrix,
        max_luna=max_luna,
    )


# ---------------------------------------------------------------------------
# Export PPT
# ---------------------------------------------------------------------------

@reports_bp.route('/export/ppt/dashboard')
def export_ppt_dashboard():
    an = int(request.args.get('an', datetime.date.today().year))
    kpis_raw = queries.kpi_cards()
    kpis = {r['an']: r for r in kpis_raw}
    cy = kpis.get(an, {})
    py = kpis.get(an - 1, {})
    delta_vn   = _delta_pct(cy.get('val_neta', 0), py.get('val_neta', 0))
    delta_mb   = _delta_pct(cy.get('marja_bruta', 0), py.get('marja_bruta', 0))
    delta_mn   = _delta_pct(cy.get('marja_neta', 0), py.get('marja_neta', 0))
    delta_mpct = round((cy.get('marja_pct', 0) or 0) - (py.get('marja_pct', 0) or 0), 1)
    agents   = queries.profitabilitate_agenti(an)
    clients  = queries.profitabilitate_clienti(an, limit=15)
    kaufland = queries.risk_kaufland(an)
    bogdan   = queries.risk_agent(an, 'DRAGNEA BOGDAN')
    churn    = queries.churn_clients(60)
    trend_by_year = _build_trend_series(queries.monthly_trend())
    brands   = queries.brand_mix(an)
    channels = queries.channel_mix(an)
    buf = ppt_export.build_dashboard_ppt(
        an, cy, py, delta_vn, delta_mb, delta_mn, delta_mpct,
        agents, clients, kaufland, bogdan, churn,
        trend_by_year=trend_by_year,
        brands_data=brands,
        channels_data=channels,
    )
    return ppt_export.send_ppt(buf, ppt_export.timestamped_filename(f'dashboard_{an}'))


@reports_bp.route('/export/ppt/agent')
def export_ppt_agent():
    name = request.args.get('name', '').strip()
    an   = int(request.args.get('an', datetime.date.today().year))
    if not name:
        abort(404)
    kpi    = queries.agent_kpi(name, an) or {}
    kpi_py = queries.agent_kpi(name, an - 1) or {}
    kpi['marja_neta_pct'] = round(
        (kpi.get('marja_neta') or 0) * 100 / (kpi.get('val_neta') or 1), 1
    )
    clients = queries.agent_clients_full(name, an)
    brands  = queries.agent_brands_full(name, an)
    skus    = queries.agent_skus_full(name, an)
    buf = ppt_export.build_agent_ppt(name, an, kpi, kpi_py, clients, brands, skus)
    safe = name.replace(' ', '_').replace('/', '_')
    return ppt_export.send_ppt(buf, ppt_export.timestamped_filename(f'agent_{safe}_{an}'))


@reports_bp.route('/export/ppt/client')
def export_ppt_client():
    cod = request.args.get('cod_client', '').strip()
    an  = int(request.args.get('an', datetime.date.today().year))
    if not cod:
        abort(404)
    info = queries.client_info(cod)
    if not info:
        abort(404)
    products = queries.client_products_full(cod, an)
    yearly   = queries.client_yearly_full(cod)
    buf = ppt_export.build_client_ppt(info['client'], an, dict(info), products, yearly)
    safe = (info['client'] or cod).replace(' ', '_').replace('/', '_')[:25]
    return ppt_export.send_ppt(buf, ppt_export.timestamped_filename(f'client_{safe}'))


@reports_bp.route('/export/ppt/profitabilitate')
def export_ppt_profitabilitate():
    an = int(request.args.get('an', datetime.date.today().year))
    agents   = queries.profitabilitate_agenti(an)
    clients  = queries.profitabilitate_clienti(an)
    products = queries.profitabilitate_produse(an)
    buf = ppt_export.build_profitabilitate_ppt(an, agents, clients, products)
    return ppt_export.send_ppt(buf, ppt_export.timestamped_filename(f'profitabilitate_{an}'))


# ---------------------------------------------------------------------------
# Export Excel — rapoarte
# ---------------------------------------------------------------------------

def _urgenta_label(zile_stoc):
    if zile_stoc is None:
        return 'OK'
    if zile_stoc < 30:
        return 'Critic'
    if zile_stoc < 60:
        return 'Atenție'
    return 'OK'


def _forecast_export_row(r):
    """Aplatizează un rând din forecast_stoc_extended în coloane de export,
    identice cu ce arată pagina. Vânz./lună = media sezonieră pe fereastra
    istorică configurată."""
    row = {
        'Cod furnizor':    r.get('cod_produs') or '',
        'SKU':             r.get('sku') or '',
        'Brand':           r.get('gama') or r.get('furnizor') or '',
        'Stoc (buc)':      r.get('stoc_total') or 0,
        'Val. stoc':       r.get('valoare_stoc') or 0,
        'În tranzit':      r.get('in_tranzit_qty') or 0,
        'Vânz./lună':      r.get('vanzari_luna_avg') or 0,
        'Zile stoc':       r.get('zile_stoc') if r.get('zile_stoc') is not None else '',
        'Urgență':         _urgenta_label(r.get('zile_stoc')),
        'Sug. RO':         r.get('suggested_ro') or 0,
    }
    # Sugestii per piață export (model client×articol); fallback pe totalul HU.
    sug_piete = r.get('sug_piete') or {}
    if sug_piete:
        for piata, val in sug_piete.items():
            row[f'Sug. {piata}'] = val or 0
    else:
        row['Sug. HU'] = r.get('suggested_hu') or 0
    row['Cel mai vechi lot'] = r.get('cel_mai_vechi_lot') or ''
    return row


@reports_bp.route('/export/<report>')
def export_excel(report):
    an = int(request.args.get('an', datetime.date.today().year))

    if report == 'dashboard':
        sheets = {
            'KPI': queries.kpi_cards(),
            'Brand Mix': queries.brand_mix(an),
            'Canale': queries.channel_mix(an),
            'Trend Lunar': queries.monthly_trend(),
            'Top 10 Clienți': queries.top_clients(an),
            'Churn (>60z)': queries.churn_clients(60),
        }
        return send_excel(sheets, timestamped_filename(f'dashboard_{an}'))

    if report == 'team':
        rows_cy = queries.team_table(an)
        rows_py = queries.team_table(an - 1)
        return send_excel(
            {f'Echipa {an}': rows_cy, f'Echipa {an-1}': rows_py},
            timestamped_filename(f'echipa_{an}'),
        )

    if report == 'clients':
        search = request.args.get('q', '').strip() or None
        agent  = request.args.get('agent', '').strip() or None
        churn  = request.args.get('churn', '').strip() or None
        brand  = request.args.get('brand', '').strip() or None
        rows = queries.clients_list(an, search=search, agent=agent, churn=churn, brand=brand)
        return send_excel(
            {f'Clienți {an}': rows},
            timestamped_filename(f'clienti_{an}'),
        )

    if report == 'products':
        furnizor = request.args.get('brand', '').strip() or None
        brand_rows = queries.products_brands(an)
        sku_rows   = queries.products_top_skus(an, furnizor=furnizor)
        return send_excel(
            {'Branduri': brand_rows, 'Top SKU': sku_rows},
            timestamped_filename(f'produse_{an}'),
        )

    if report == 'forecast':
        gama     = request.args.get('gama', '').strip() or None
        urgenta  = request.args.get('urgenta', '').strip() or None
        furnizor = request.args.get('brand', '').strip() or None
        search   = request.args.get('q', '').strip() or None
        # Aceleași date ca pagina, ca exportul să coincidă cu ecranul.
        rows = queries.forecast_stoc_extended(
            furnizor=furnizor, gama=gama, urgenta=urgenta, search=search)
        export_rows = [_forecast_export_row(r) for r in rows]
        return send_excel(
            {'Forecast Stoc': export_rows},
            timestamped_filename('forecast_stoc'),
        )

    if report == 'preturi':
        furnizor  = request.args.get('furnizor', '').strip() or None
        search    = request.args.get('q', '').strip() or None
        sub_marja = request.args.get('sub_marja', '').strip()
        sub_marja = float(sub_marja) if sub_marja else None
        fara_pret = request.args.get('fara_pret', '') == '1'
        rows = queries.preturi_catalog(an, furnizor, search, fara_pret, sub_marja)
        return send_excel(
            {'Catalog Prețuri': rows},
            timestamped_filename(f'preturi_{an}'),
        )

    if report == 'conditii':
        cod_client = request.args.get('client', '').strip() or None
        furnizor   = request.args.get('brand', '').strip() or None
        sheets = {
            'Condiții': queries.conditii_list(an, cod_client, furnizor),
            'Termene Plată': queries.termene_list(an, cod_client),
            'Marjă Ajustată': queries.marja_ajustata(an),
        }
        return send_excel(sheets, timestamped_filename(f'conditii_{an}'))

    if report == 'agent':
        name = request.args.get('name', '').strip()
        if not name:
            abort(404)
        sheets = {
            'KPI Agent': [queries.agent_kpi(name, an) or {}],
            f'Clienți {an}': queries.agent_clients(name, an),
            f'Top SKU {an}': queries.agent_top_skus(name, an),
            'Trend Lunar': queries.agent_monthly_trend(name),
        }
        safe_name = name.replace(' ', '_').replace('/', '_')
        return send_excel(sheets, timestamped_filename(f'agent_{safe_name}_{an}'))

    if report == 'client':
        cod = request.args.get('cod_client', '').strip()
        if not cod:
            abort(404)
        info = queries.client_info(cod)
        if not info:
            abort(404)
        luna_exp = int(request.args.get('luna', 0)) or None
        max_luna_exp = None if luna_exp else queries.max_luna_for_year(an)
        sheets = {
            'Informații': [dict(info)],
            f'Produse {an}': queries.client_products_full(cod, an, luna=luna_exp, max_luna=max_luna_exp),
            'Brand Mix': queries.client_brand_mix(cod, an),
            'Evoluție Anuală': queries.client_yearly_full(cod),
        }
        safe_client = (info.get('client', cod) or cod).replace(' ', '_').replace('/', '_')[:30]
        return send_excel(sheets, timestamped_filename(f'client_{safe_client}'))

    if report == 'produs':
        sku = request.args.get('sku', '').strip()
        if not sku:
            abort(404)
        kpi = queries.product_kpi(sku, an)
        if not kpi:
            abort(404)
        sheets = {
            'KPI': [dict(kpi)],
            f'Clienți {an}': queries.product_clients(sku, an),
            'Evoluție Anuală': queries.product_yearly(sku),
            'Trend Lunar': queries.product_monthly(sku),
        }
        safe_sku = sku.replace(' ', '_').replace('/', '_')[:30]
        return send_excel(sheets, timestamped_filename(f'produs_{safe_sku}_{an}'))

    if report == 'profitabilitate':
        sheets = {
            f'Agenți {an}': queries.profitabilitate_agenti(an),
            f'Clienți {an}': queries.profitabilitate_clienti(an),
            f'Produse {an}': queries.profitabilitate_produse(an),
            'Matrice Agent×Brand': queries.profitabilitate_matrice(an),
        }
        return send_excel(sheets, timestamped_filename(f'profitabilitate_{an}'))

    abort(404)


# ---------------------------------------------------------------------------
# Raportare Basilur
# ---------------------------------------------------------------------------

BASILUR_BRANDS = ['Basilur', 'KingsLeaf', 'Tipson', 'Organsia']


def _basilur_monthly_matrix(rows, an):
    """Convertește rows (furnizor, luna, val_neta) în {furnizor: [12 valori]}."""
    out = {b: [0] * 12 for b in BASILUR_BRANDS}
    for r in rows:
        furn = r['furnizor']
        luna = r['luna']
        if furn in out and luna and 1 <= int(luna) <= 12:
            out[furn][int(luna) - 1] = r['val_neta'] or 0
    return out


@reports_bp.route('/raportare-basilur')
def raportare_basilur():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)

    if luna:
        max_luna = None
        period_label = f"{MONTHS_RO[luna - 1]} {an}"
        period_label_py = f"{MONTHS_RO[luna - 1]} {an - 1}"
    else:
        max_luna = queries.max_luna_for_year(an)
        period_label = f"{an} YTD (ian–{MONTHS_RO[(max_luna or 1) - 1]})"
        period_label_py = f"{an - 1} YTD"

    kpi_total     = queries.basilur_kpi_total(an, max_luna=max_luna, luna=luna) or {}
    kpi_per_brand = queries.basilur_kpi_per_brand(an, max_luna=max_luna, luna=luna)
    kpi_py_total  = queries.basilur_kpi_total(an - 1, max_luna=max_luna, luna=luna) or {}
    monthly_rows  = queries.basilur_monthly_per_brand(an)
    monthly_data  = _basilur_monthly_matrix(monthly_rows, an)
    stoc_per_brand = queries.basilur_stoc_per_brand()
    stoc_total     = queries.basilur_stoc_total()

    usd_rate = request.args.get('curs', type=float, default=4.55)

    kpi_map = {r['furnizor']: dict(r) for r in kpi_per_brand}
    for b in BASILUR_BRANDS:
        if b not in kpi_map:
            kpi_map[b] = {'furnizor': b, 'val_neta': 0, 'marja_bruta': 0,
                          'marja_pct': 0, 'clienti_activi': 0, 'nr_sku': 0,
                          'val_neta_py': 0, 'delta_vn': None}

    stoc_map = {r['furnizor']: dict(r) for r in stoc_per_brand}
    for b in BASILUR_BRANDS:
        if b not in stoc_map:
            stoc_map[b] = {'furnizor': b, 'nr_sku': 0, 'total_unitati': 0,
                           'valoare_achizitie': 0}

    return render_template(
        'raportare_basilur.html',
        an=an, luna=luna, max_luna=max_luna,
        period_label=period_label, period_label_py=period_label_py,
        kpi_total=dict(kpi_total), kpi_py_total=dict(kpi_py_total),
        kpi_map=kpi_map,
        monthly_data_json=json.dumps(monthly_data),
        months_json=json.dumps(MONTHS_RO),
        stoc_map=stoc_map, stoc_total=dict(stoc_total),
        basilur_brands=BASILUR_BRANDS,
        usd_rate=usd_rate,
    )


@reports_bp.route('/raportare-basilur/export/excel')
def raportare_basilur_excel():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)
    max_luna = None if luna else queries.max_luna_for_year(an)

    kpi_per_brand  = queries.basilur_kpi_per_brand(an, max_luna=max_luna, luna=luna)
    monthly_rows   = queries.basilur_monthly_per_brand(an)
    stoc_per_brand = queries.basilur_stoc_per_brand()
    stoc_detail    = queries.basilur_stoc_detail()

    R = request.args.get('curs', type=float, default=4.55)

    # Sheet 1: KPI per brand
    kpi_rows = [{
        'Brand':             r['furnizor'],
        'Net Sales (USD)':   round((r['val_neta'] or 0) / R, 0),
        'Active Clients':    r['clienti_activi'] or 0,
        'Active SKUs':       r['nr_sku'] or 0,
        'Net Sales PY (USD)': round((r['val_neta_py'] or 0) / R, 0),
        'YoY Delta %':       r['delta_vn'],
    } for r in kpi_per_brand]

    # Sheet 2: Monthly evolution (pivot: brand x month)
    MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    monthly_matrix = _basilur_monthly_matrix(monthly_rows, an)
    pivot_rows = []
    for brand in BASILUR_BRANDS:
        vals = monthly_matrix.get(brand, [0] * 12)
        row = {'Brand': brand}
        for i, m in enumerate(MONTHS_EN):
            row[m] = round(vals[i] / R, 0)
        row['TOTAL'] = round(sum(vals) / R, 0)
        pivot_rows.append(row)
    total_row = {'Brand': 'TOTAL'}
    for i, m in enumerate(MONTHS_EN):
        total_row[m] = round(sum(monthly_matrix.get(b, [0]*12)[i] for b in BASILUR_BRANDS) / R, 0)
    total_row['TOTAL'] = sum(total_row[m] for m in MONTHS_EN)
    pivot_rows.append(total_row)
    luni_headers = ['Brand'] + MONTHS_EN + ['TOTAL']

    # Sheet 3: Stock per brand
    stoc_brand_rows = [{
        'Brand':                  r['furnizor'],
        'SKU Count':              r['nr_sku'] or 0,
        'Total Units':            r['total_unitati'] or 0,
        'Acquisition Value (USD)': round((r['valoare_achizitie'] or 0) / R, 0),
    } for r in stoc_per_brand]

    # Sheet 4: Stock detail per SKU
    stoc_sku_rows = [{
        'Brand':                  r['furnizor'],
        'Product Code':           r['cod_produs'],
        'SKU':                    r['sku'],
        'Quantity':               r['cantitate'] or 0,
        'Unit Cost (USD)':        round((r['pret_achizitie'] or 0) / R, 2),
        'Acquisition Value (USD)': round((r['valoare_achizitie'] or 0) / R, 0),
        'Days in Stock':          r['nr_zile_stoc'],
        'Entry Date':             r['data_intrare'],
    } for r in stoc_detail]

    sheets = {
        'Brand KPIs':     {'rows': kpi_rows,        'headers': list(kpi_rows[0].keys()) if kpi_rows else []},
        'Monthly Sales':  {'rows': pivot_rows,       'headers': luni_headers},
        'Stock by Brand': {'rows': stoc_brand_rows,  'headers': list(stoc_brand_rows[0].keys()) if stoc_brand_rows else []},
        'Stock Detail':   {'rows': stoc_sku_rows,    'headers': list(stoc_sku_rows[0].keys()) if stoc_sku_rows else []},
    }
    period_str = f"{MONTHS_EN[luna - 1]}_{an}" if luna else f"{an}_YTD"
    return send_excel(sheets, timestamped_filename(f'basilur_report_{period_str}'))


@reports_bp.route('/raportare-basilur/export/ppt')
def raportare_basilur_ppt():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)
    max_luna = None if luna else queries.max_luna_for_year(an)

    if luna:
        period_label = f"{MONTHS_RO[luna - 1]} {an}"
    else:
        ml = max_luna or 1
        period_label = f"{an} YTD (ian–{MONTHS_RO[ml - 1]})"

    kpi_total      = queries.basilur_kpi_total(an, max_luna=max_luna, luna=luna) or {}
    kpi_per_brand  = queries.basilur_kpi_per_brand(an, max_luna=max_luna, luna=luna)
    monthly_rows   = queries.basilur_monthly_per_brand(an)
    monthly_data   = _basilur_monthly_matrix(monthly_rows, an)
    stoc_per_brand = queries.basilur_stoc_per_brand()
    stoc_detail    = queries.basilur_stoc_detail()

    buf = ppt_export.build_basilur_ppt(
        an=an,
        period_label=period_label,
        kpi_total=dict(kpi_total),
        kpi_per_brand=[dict(r) for r in kpi_per_brand],
        monthly_data=monthly_data,
        stoc_per_brand=[dict(r) for r in stoc_per_brand],
        stoc_detail=[dict(r) for r in stoc_detail],
    )
    period_str = f"{MONTHS_RO[luna - 1]}_{an}" if luna else f"{an}_YTD"
    return ppt_export.send_ppt(buf, ppt_export.timestamped_filename(
        f'raportare_basilur_{period_str}'))


# ---------------------------------------------------------------------------
# Export comenzi (intern + furnizor) și expirare stoc
# ---------------------------------------------------------------------------

@reports_bp.route('/export/comenzi/<int:comanda_id>')
def export_comanda_intern(comanda_id):
    from exports.excel_export import export_comenzi_intern
    cmd = queries.query_one("SELECT nr_comanda, furnizor FROM comenzi_furnizori WHERE id=?", (comanda_id,))
    if not cmd:
        return "Comanda nu există", 404
    out = export_comenzi_intern(comanda_id)
    fname = f"comanda_{cmd['nr_comanda']}_{cmd['furnizor']}.xlsx"
    return send_file(out, download_name=fname, as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@reports_bp.route('/export/comenzi/<int:comanda_id>/furnizor')
def export_comanda_furnizor(comanda_id):
    from exports.excel_export import export_comenzi_basilur, export_comenzi_intern
    cmd = queries.query_one("SELECT nr_comanda, furnizor FROM comenzi_furnizori WHERE id=?", (comanda_id,))
    if not cmd:
        return "Comanda nu există", 404
    basilur_fam = {'Basilur', 'KingsLeaf', 'Kings Leaf', 'Tipson', 'Organsia'}
    if cmd['furnizor'] in basilur_fam:
        out = export_comenzi_basilur(comanda_id)
    else:
        out = export_comenzi_intern(comanda_id)
    fname = f"order_{cmd['nr_comanda']}_{cmd['furnizor']}.xlsx"
    return send_file(out, download_name=fname, as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@reports_bp.route('/export/expirare')
def export_expirare_view():
    from exports.excel_export import export_expirare
    brand = request.args.get('brand', '') or None
    prag  = int(request.args.get('prag', 6))
    out   = export_expirare(furnizor=brand, prag_luni=prag)
    return send_file(out, download_name='expirare_stoc.xlsx', as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

