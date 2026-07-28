import datetime
import json
import logging
from flask import Blueprint, render_template, request, abort, send_file, redirect, url_for
from flask_login import current_user
import authz
import queries
from exports import entities, overviews, ppt_export
from exports.excel_export import send_excel, timestamped_filename

reports_bp = Blueprint('reports', __name__)

logger = logging.getLogger(__name__)

_EXPORT_NAV_KEY = {
    "dashboard": "dashboard",
    "team": "team",
    "agent": "team",
    "clients": "clients",
    "client": "clients",
    "products": "products",
    "produs": "products",
    "brand": "products",
    "forecast": "forecast",
    "preturi": "preturi",
    "conditii": "conditii",
    "profitabilitate": "profitabilitate",
    "basilur": "basilur",
}

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
    # Same physical product can exist under several tranzactii spellings
    # (ERP vs Tobra/Auchan file) — aggregate the whole page over all of them.
    variants = queries.sku_variants(sku)
    kpi     = queries.product_kpi(variants, an, luna=luna, max_luna=max_luna)
    kpi_py  = queries.product_kpi(variants, an - 1, luna=luna, max_luna=max_luna)
    if not kpi:
        abort(404)
    kpi['delta_vn'] = _delta_pct(kpi.get('val_neta', 0), (kpi_py or {}).get('val_neta', 0))

    clients = queries.product_clients(variants, an, luna=luna, max_luna=max_luna)
    clients_istoric, istoric_years = queries.product_clients_istoric(variants)
    monthly = queries.product_monthly(variants)
    yearly  = queries.product_yearly(variants)

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
        sku_variants=[v for v in variants if v != sku],
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

# (nav key, request arg carrying the entity id — None for overview decks)
def _overview_filters(report):
    """Query args each overview export honours - one source of truth for both
    dispatchers, so the Excel and PPT links cannot disagree about the filter."""
    if report == 'clients':
        return {k: request.args.get(k, '').strip()
                for k in ('q', 'agent', 'churn', 'brand')}
    if report == 'products':
        return {k: request.args.get(k, '').strip() for k in ('brand', 'q')}
    if report == 'basilur':
        return {'curs': request.args.get(
            'curs', type=float, default=overviews.BASILUR_DEFAULT_CURS)}
    return {}


_PPT_ENTITIES = {
    'dashboard':       ('dashboard', None),
    'profitabilitate': ('profitabilitate', None),
    'client':          ('clients', 'cod_client'),
    'agent':           ('team', 'name'),
    'brand':           ('products', 'furnizor'),
    'produs':          ('products', 'sku'),
}


def _dashboard_ppt(an):
    kpis = {r['an']: r for r in queries.kpi_cards()}
    cy = kpis.get(an, {})
    py = kpis.get(an - 1, {})
    delta_vn = _delta_pct(cy.get('val_neta', 0), py.get('val_neta', 0))
    delta_mb = _delta_pct(cy.get('marja_bruta', 0), py.get('marja_bruta', 0))
    delta_mn = _delta_pct(cy.get('marja_neta', 0), py.get('marja_neta', 0))
    delta_mpct = round((cy.get('marja_pct', 0) or 0) - (py.get('marja_pct', 0) or 0), 1)
    buf = ppt_export.build_dashboard_ppt(
        an, cy, py, delta_vn, delta_mb, delta_mn, delta_mpct,
        queries.profitabilitate_agenti(an),
        queries.profitabilitate_clienti(an, limit=15),
        queries.risk_kaufland(an),
        queries.risk_agent(an, 'DRAGNEA BOGDAN'),
        queries.churn_clients(60),
        trend_by_year=_build_trend_series(queries.monthly_trend()),
        brands_data=queries.brand_mix(an),
        channels_data=queries.channel_mix(an),
    )
    return buf, f'dashboard_{an}'


def _profitabilitate_ppt(an):
    buf = ppt_export.build_profitabilitate_ppt(
        an,
        queries.profitabilitate_agenti(an),
        queries.profitabilitate_clienti(an),
        queries.profitabilitate_produse(an),
    )
    return buf, f'profitabilitate_{an}'


_OVERVIEW_PPT = {
    'dashboard': _dashboard_ppt,
    'profitabilitate': _profitabilitate_ppt,
}


@reports_bp.route('/export/ppt/<entity>')
def export_ppt(entity):
    """Generic multi-feature PPT export - gated per-entity here, which is why
    this endpoint is allow-listed in nav_registry.UNGATED_ENDPOINTS."""
    known = entity in overviews.REPORTS or entity in _PPT_ENTITIES
    nav = _EXPORT_NAV_KEY.get(entity)
    if not known or nav is None:
        abort(404)
    if not authz.can_access_nav(current_user.role, nav):
        abort(403)

    an = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int)

    if entity in overviews.REPORTS:
        ctx = overviews.build_context(entity, an, luna, _overview_filters(entity))
        if ctx is None:
            abort(404)
        builder = ctx.get('ppt_builder')
        buf = builder() if builder else ppt_export.build_entity_ppt(ctx)
        return ppt_export.send_ppt(
            buf, ppt_export.timestamped_filename(ctx['filename_base']))

    param = _PPT_ENTITIES[entity][1]
    if param is None:
        buf, base = _OVERVIEW_PPT[entity](an)
        return ppt_export.send_ppt(buf, ppt_export.timestamped_filename(base))

    ident = request.args.get(param, '').strip()
    ctx = entities.build_context(entity, ident, an, luna) if ident else None
    if ctx is None:
        abort(404)
    buf = ppt_export.build_entity_ppt(ctx)
    return ppt_export.send_ppt(
        buf, ppt_export.timestamped_filename(ctx['filename_base']))


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

    _nav = _EXPORT_NAV_KEY.get(report)
    if _nav and not authz.can_access_nav(current_user.role, _nav):
        abort(403)

    if report in overviews.REPORTS:
        luna = request.args.get('luna', type=int)
        ctx = overviews.build_context(report, an, luna, _overview_filters(report))
        if ctx is None:
            abort(404)
        return send_excel(ctx['sheets'],
                          timestamped_filename(ctx['filename_base']))

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

    if report in entities.ENTITIES:
        param = _PPT_ENTITIES[report][1]
        ident = request.args.get(param, '').strip()
        luna = request.args.get('luna', type=int)
        ctx = entities.build_context(report, ident, an, luna) if ident else None
        if ctx is None:
            abort(404)
        return send_excel(ctx['sheets'],
                          timestamped_filename(ctx['filename_base']))

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
    monthly_data  = overviews.basilur_monthly_matrix(monthly_rows)
    stoc_per_brand = queries.basilur_stoc_per_brand()
    stoc_total     = queries.basilur_stoc_total()

    usd_rate = request.args.get('curs', type=float,
                                default=overviews.BASILUR_DEFAULT_CURS)

    kpi_map = {r['furnizor']: dict(r) for r in kpi_per_brand}
    for b in overviews.BASILUR_BRANDS:
        if b not in kpi_map:
            kpi_map[b] = {'furnizor': b, 'val_neta': 0, 'marja_bruta': 0,
                          'marja_pct': 0, 'clienti_activi': 0, 'nr_sku': 0,
                          'val_neta_py': 0, 'delta_vn': None}

    stoc_map = {r['furnizor']: dict(r) for r in stoc_per_brand}
    for b in overviews.BASILUR_BRANDS:
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
        basilur_brands=overviews.BASILUR_BRANDS,
        usd_rate=usd_rate,
    )


def _forward_args(*drop):
    args = request.args.to_dict()
    for key in drop:
        args.pop(key, None)
    return args


@reports_bp.route('/raportare-basilur/export/excel')
def raportare_basilur_excel():
    """Kept so bookmarked links survive - the export moved to the generic
    dispatcher, which is the only place that builds a basilur context."""
    return redirect(url_for('reports.export_excel', report='basilur',
                            **_forward_args('report')))


@reports_bp.route('/raportare-basilur/export/ppt')
def raportare_basilur_ppt():
    """Kept so bookmarked links survive - see raportare_basilur_excel."""
    return redirect(url_for('reports.export_ppt', entity='basilur',
                            **_forward_args('entity')))


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

