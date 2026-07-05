import datetime
import logging
from flask import Blueprint, render_template, request, jsonify, abort
import queries
import pricing_engine

pricing_bp = Blueprint('pricing', __name__)

logger = logging.getLogger(__name__)


@pricing_bp.route('/preturi')
def preturi():
    an        = int(request.args.get('an', datetime.date.today().year))
    furnizor  = request.args.get('furnizor', '').strip() or None
    search    = request.args.get('q', '').strip() or None
    tab       = request.args.get('tab', 'catalog')
    sub_marja = request.args.get('sub_marja', '').strip()
    sub_marja = float(sub_marja) if sub_marja else None
    fara_pret = request.args.get('fara_pret', '') == '1'

    catalog       = queries.preturi_catalog(an, furnizor, search, fara_pret, sub_marja)
    furnizori     = queries.furnizori_list()
    rate          = {r['moneda']: r['curs_ron'] for r in queries.rate_schimb_list(an)}

    return render_template('preturi.html',
        an=an, tab=tab,
        catalog=catalog, furnizori=furnizori, rate=rate,
        sel_furnizor=furnizor or '', q=search or '',
        sub_marja=sub_marja or '', fara_pret=fara_pret,
    )


@pricing_bp.route('/preturi/<path:sku>')
def preturi_sku(sku):
    an   = int(request.args.get('an', datetime.date.today().year))
    prod = queries.preturi_sku(sku, an)
    if not prod:
        abort(404)
    client_prices = queries.preturi_client_sku(sku, an)
    rate          = {r['moneda']: r['curs_ron'] for r in queries.rate_schimb_list(an)}
    client_opts   = queries.clients_list(an)
    praguri       = pricing_engine.praguri_marja(prod['gama'])
    cond_map      = {pv['cod_client']: pricing_engine.cond_effective(
                        an, pv['cod_client'], prod['furnizor'], prod['categorie'], sku)
                     for pv in client_prices if pv['cod_client']}
    return render_template('preturi_sku.html',
        an=an, prod=prod, client_prices=client_prices,
        rate=rate, client_opts=client_opts, praguri=praguri, cond_map=cond_map,
    )


@pricing_bp.route('/api/preturi/landing', methods=['POST'])
def api_preturi_landing():
    d = request.get_json(silent=True) or {}
    try:
        landing = queries.preturi_update_landing(
            d['sku'], int(d['an']),
            float(d['pret_valuta']), d['moneda'], float(d['curs']),
            float(d.get('transport_pct', 10)),
            float(d.get('taxa_vamala_pct', 0)),
            float(d.get('alte_costuri', 0)),
        )
        return jsonify({'ok': True, 'landing_cost_ron': landing})
    except Exception as e:
        logger.exception("api_preturi_landing failed")
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/api/preturi/vanzare', methods=['POST'])
def api_preturi_vanzare():
    d = request.get_json(silent=True) or {}
    try:
        queries.preturi_update_vanzare(
            d['sku'], int(d['an']), float(d['pret']),
            d.get('cod_client') or None,
        )
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception("api_preturi_vanzare failed")
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/api/preturi/produs', methods=['POST'])
def api_preturi_produs():
    d = request.get_json(silent=True) or {}
    try:
        queries.preturi_update_produs(
            d['sku'], d.get('hs_code'), float(d.get('taxa_mfn', 0)),
            float(d.get('taxa_aplicata', 0)), float(d.get('tva_pct', 0.09)),
        )
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception("api_preturi_produs failed")
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/api/preturi/curs', methods=['POST'])
def api_preturi_curs():
    d = request.get_json(silent=True) or {}
    try:
        queries.rate_schimb_update(int(d['an']), d['moneda'], float(d['curs']))
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception("api_preturi_curs failed")
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/api/preturi/simuleaza', methods=['POST'])
def api_preturi_simuleaza():
    d = request.get_json(silent=True) or {}
    try:
        pret_nou = float(d['pret_nou'])
        landing  = float(d['landing_cost'])
        marja_b  = pret_nou - landing
        marja_b_pct = marja_b / pret_nou * 100 if pret_nou else 0
        cost_cond = float(d.get('cost_conditii', 0))
        marja_n   = marja_b - cost_cond
        marja_n_pct = marja_n / pret_nou * 100 if pret_nou else 0
        return jsonify({
            'ok': True,
            'marja_bruta_ron': round(marja_b, 4),
            'marja_bruta_pct': round(marja_b_pct, 2),
            'marja_neta_ron':  round(marja_n, 4),
            'marja_neta_pct':  round(marja_n_pct, 2),
        })
    except Exception as e:
        logger.exception("api_preturi_simuleaza failed")
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/conditii')
def conditii():
    an          = int(request.args.get('an', datetime.date.today().year))
    cod_client  = request.args.get('client', '').strip() or None
    furnizor    = request.args.get('brand', '').strip() or None
    tab         = request.args.get('tab', 'conditii')

    cond_rows   = queries.conditii_list(an, cod_client, furnizor)
    termen_rows = queries.termene_list(an, cod_client)
    analiza     = queries.marja_ajustata(an) if tab == 'analiza' else []
    client_opts = queries.clients_list(an)
    brand_opts  = queries.brands_list()

    return render_template(
        'conditii.html',
        an=an, tab=tab,
        cond_rows=cond_rows,
        termen_rows=termen_rows,
        analiza=analiza,
        client_opts=client_opts,
        brand_opts=brand_opts,
        sel_client=cod_client or '',
        sel_brand=furnizor or '',
    )


@pricing_bp.route('/api/conditii', methods=['POST'])
def api_conditii_create():
    d = request.get_json(silent=True) or {}
    try:
        queries.conditii_create(
            int(d['an']), d.get('cod_client'), d.get('furnizor'),
            d['tip_valoare'], d['periodicitate'], float(d['valoare']),
            d.get('descriere'),
        )
        queries.rebuild_cond_resolved()
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception("api_conditii_create failed")
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/api/conditii/<int:id>', methods=['PUT'])
def api_conditii_update(id):
    d = request.get_json(silent=True) or {}
    try:
        queries.conditii_update(
            id, int(d['an']), d.get('cod_client'), d.get('furnizor'),
            d['tip_valoare'], d['periodicitate'], float(d['valoare']),
            d.get('descriere'),
        )
        queries.rebuild_cond_resolved()
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception("api_conditii_update id=%s failed", id)
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/api/conditii/<int:id>', methods=['DELETE'])
def api_conditii_delete(id):
    queries.conditii_delete(id)
    queries.rebuild_cond_resolved()
    return jsonify({'ok': True})


@pricing_bp.route('/api/termene', methods=['POST'])
def api_termene_create():
    d = request.get_json(silent=True) or {}
    try:
        queries.termene_create(int(d['an']), d['cod_client'],
                               int(d['zile_termen']), d.get('observatii'))
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception("api_termene_create failed")
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/api/termene/<int:id>', methods=['DELETE'])
def api_termene_delete(id):
    queries.termene_delete(id)
    return jsonify({'ok': True})
