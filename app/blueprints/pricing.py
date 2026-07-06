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
        poza=queries.produs_poza(sku),
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


# ── Articol nou (F2) ─────────────────────────────────────────────────────────

@pricing_bp.route('/preturi/nou')
def preturi_articol_nou():
    an = int(request.args.get('an', datetime.date.today().year))
    rate = {r['moneda']: r['curs_ron'] for r in queries.rate_schimb_list(an)}
    return render_template('preturi_nou.html', an=an, rate=rate,
                           atribute=queries.produse_atribute_distincte())


@pricing_bp.route('/api/preturi/articol-nou', methods=['POST'])
def api_preturi_articol_nou():
    d = request.get_json(silent=True) or {}
    try:
        err = queries.produs_create(d)
        if err:
            return jsonify({'error': err}), 400
        return jsonify({'ok': True, 'sku': d['sku'].strip()})
    except Exception as e:
        logger.exception("api_preturi_articol_nou failed")
        return jsonify({'error': str(e)}), 400


# ── Simulator + propuneri de pret (F2) ───────────────────────────────────────

@pricing_bp.route('/preturi/simulator')
def preturi_simulator():
    an         = int(request.args.get('an', datetime.date.today().year))
    cod_client = request.args.get('client', '').strip() or None
    client_opts = list(queries.clients_list(an))
    cunoscuti   = {c['cod_client'] for c in client_opts}
    client_opts += [{'cod_client': p['cod_client'],
                     'client': p['nume_client'] + ' [prospect]'}
                    for p in queries.clienti_prospecti_list()
                    if p['cod_client'] not in cunoscuti]
    articole, cond_map, praguri = [], {}, pricing_engine.praguri_marja()
    if cod_client:
        articole = queries.simulator_articole(an, cod_client)
        cond_map = pricing_engine.cond_map_for_client(an, cod_client, articole)
    propuneri = queries.propuneri_list(an, cod_client)
    return render_template('preturi_simulator.html',
        an=an, cod_client=cod_client or '', client_opts=client_opts,
        articole=articole, cond_map=cond_map, praguri=praguri,
        propuneri=propuneri)


@pricing_bp.route('/api/preturi/propuneri', methods=['POST'])
def api_propunere_create():
    d = request.get_json(silent=True) or {}
    try:
        an, cod_client = int(d['an']), d['cod_client']
        linii_in = {li['sku']: float(li['pret_propus'])
                    for li in d.get('linii', []) if li.get('pret_propus')}
        if not linii_in:
            return jsonify({'error': 'Nicio linie cu preț propus.'}), 400
        articole = {a['sku']: a for a in queries.simulator_articole(an, cod_client)}
        cond_map = pricing_engine.cond_map_for_client(an, cod_client,
                                                      list(articole.values()))
        linii = []
        for sku, pret in linii_in.items():
            a = articole.get(sku)
            if a is None:
                continue
            cond    = cond_map.get(sku, 0)
            neta    = pricing_engine.marja_neta_pct(pret, a['landing_cost_ron'], cond)
            praguri = pricing_engine.praguri_marja(a['gama'])
            linii.append({
                'sku': sku, 'pret_propus': pret,
                'pret_actual': a['pret_client'] or a['pret_standard'],
                'landing_ron': a['landing_cost_ron'], 'cond_pct': cond,
                'marja_neta_pct': neta,
                'verdict': pricing_engine.verdict(neta, praguri),
            })
        pid = queries.propunere_create(an, cod_client, d.get('titlu'), linii)
        return jsonify({'ok': True, 'id': pid, 'nr_linii': len(linii)})
    except Exception as e:
        logger.exception("api_propunere_create failed")
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/api/preturi/propuneri/<int:id>')
def api_propunere_get(id):
    data = queries.propunere_get(id)
    if not data:
        abort(404)
    return jsonify({'ok': True,
                    'propunere': dict(data['propunere']),
                    'linii': [dict(li) for li in data['linii']]})


@pricing_bp.route('/api/preturi/propuneri/<int:id>', methods=['DELETE'])
def api_propunere_delete(id):
    queries.propunere_delete(id)
    return jsonify({'ok': True})


# ── F3: fisiere client din propuneri (listare / oferta cu poze) ─────────────

def _propunere_export_data(id):
    data = queries.propunere_linii_export(id)
    if not data:
        abort(404)
    return data


def _send_wb(wb, filename):
    from io import BytesIO
    from flask import send_file
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@pricing_bp.route('/preturi/propuneri/<int:id>/listare.xlsx')
def propunere_listare_xlsx(id):
    from exports import listare_export
    data     = _propunere_export_data(id)
    template = request.args.get('template') or data['template'] or 'generic'
    valabil  = request.args.get('valabil') or ''
    wb = listare_export.build_listare(data, template, valabil)
    nume = (data['nume_client'] or '').split()[0].lower() or data['propunere']['cod_client']
    return _send_wb(wb, f'lista_pret_{nume}_{valabil or id}.xlsx')


# ── Clienti prospect / poze / import oferta furnizor ────────────────────────

@pricing_bp.route('/api/preturi/clienti-prospect', methods=['POST'])
def api_client_prospect():
    d = request.get_json(silent=True) or {}
    cod, err = queries.client_prospect_create(d.get('nume'))
    if err:
        return jsonify({'error': err}), 400
    return jsonify({'ok': True, 'cod_client': cod})


@pricing_bp.route('/api/preturi/poza/<path:sku>', methods=['POST'])
def api_produs_poza(sku):
    import os
    import re as _re
    from paths import BASE_DIR
    img_dir = os.path.join(BASE_DIR, 'app', 'static', 'product_images')
    safe = _re.sub(r'[^A-Za-z0-9_-]', '_', sku)
    try:
        f = request.files.get('file')
        if f and f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                return jsonify({'error': 'Format imagine neacceptat.'}), 400
            os.makedirs(img_dir, exist_ok=True)
            rel = f'app/static/product_images/{safe}{ext}'
            f.save(os.path.join(BASE_DIR, rel))
            queries.produs_poza_set(sku, path=rel)
            return jsonify({'ok': True, 'src': f'/static/product_images/{safe}{ext}'})
        d = request.get_json(silent=True) or {}
        url = (d.get('url') or '').strip()
        if not url:
            return jsonify({'error': 'Incarca un fisier sau da un URL.'}), 400
        import requests as _rq
        resp = _rq.get(url, timeout=8)
        resp.raise_for_status()
        ext = os.path.splitext(url.split('?')[0])[1].lower()
        if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            ext = '.jpg'
        os.makedirs(img_dir, exist_ok=True)
        rel = f'app/static/product_images/{safe}{ext}'
        with open(os.path.join(BASE_DIR, rel), 'wb') as out:
            out.write(resp.content)
        queries.produs_poza_set(sku, path=rel, url_sursa=url)
        return jsonify({'ok': True, 'src': f'/static/product_images/{safe}{ext}'})
    except Exception as e:
        logger.exception("api_produs_poza failed sku=%s", sku)
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/preturi/import-oferta')
def preturi_import_oferta():
    an = int(request.args.get('an', datetime.date.today().year))
    rate = {r['moneda']: r['curs_ron'] for r in queries.rate_schimb_list(an)}
    return render_template('preturi_import_oferta.html', an=an, rate=rate,
                           atribute=queries.produse_atribute_distincte())


@pricing_bp.route('/api/preturi/import-oferta', methods=['POST'])
def api_import_oferta():
    import supplier_offer
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'Incarca fisierul cu oferta.'}), 400
    data = f.read()
    try:
        if request.form.get('actiune') == 'preview':
            return jsonify({'ok': True, **supplier_offer.preview(f.filename, data)})

        mapping = {k: request.form.get(f'col_{k}') for k in
                   ('cod', 'denumire', 'pret', 'ean', 'gramaj', 'buc_bax')}
        randuri = supplier_offer.parse_rows(
            f.filename, data, mapping, request.form.get('rand_start', 2))
        furnizor = (request.form.get('furnizor') or '').strip()
        moneda   = request.form.get('moneda', 'EUR')
        curs     = float(request.form.get('curs'))
        transport = float(request.form.get('transport_pct', 10))
        taxa      = float(request.form.get('taxa_vamala_pct', 0))
        an        = int(request.form.get('an', datetime.date.today().year))
        if not furnizor:
            return jsonify({'error': 'Numele furnizorului este obligatoriu.'}), 400
        if not randuri:
            return jsonify({'error': 'Nicio linie valida gasita - verifica '
                            'maparea coloanelor si randul de start.'}), 400

        create, sarite = 0, []
        for r in randuri:
            err = queries.produs_create({
                'sku': r['cod'], 'descriere': r['denumire'],
                'furnizor': furnizor, 'gama': furnizor, 'potential': True,
                'ean': r['ean'], 'gramaj': r['gramaj'],
                'buc_cutie': int(r['buc_bax']) if r['buc_bax'] else None,
                'logistica': {'buc_bax': int(r['buc_bax']) if r['buc_bax'] else None},
                'landing': {'an': an, 'moneda': moneda, 'pret_valuta': r['pret'],
                            'curs': curs, 'transport_pct': transport,
                            'taxa_vamala_pct': taxa},
            })
            if err:
                sarite.append(f"{r['cod']}: {err}")
            else:
                create += 1
        return jsonify({'ok': True, 'create': create, 'sarite': sarite[:30],
                        'nr_sarite': len(sarite)})
    except Exception as e:
        logger.exception("api_import_oferta failed")
        return jsonify({'error': str(e)}), 400


@pricing_bp.route('/preturi/propuneri/<int:id>/oferta.xlsx')
def propunere_oferta_xlsx(id):
    from exports import listare_export
    data    = _propunere_export_data(id)
    valabil = request.args.get('valabil') or ''
    wb = listare_export.build_oferta(data, valabil)
    nume = (data['nume_client'] or '').split()[0].lower() or data['propunere']['cod_client']
    return _send_wb(wb, f'oferta_{nume}_{valabil or id}.xlsx')


@pricing_bp.route('/preturi/propuneri/<int:id>/fisa.xlsx')
def propunere_fisa_xlsx(id):
    from exports import listare_export
    data     = _propunere_export_data(id)
    template = request.args.get('template') or 'generic'
    valabil  = request.args.get('valabil') or ''
    wb = listare_export.build_fisa(data, template, valabil)
    nume = (data['nume_client'] or '').split()[0].lower() or data['propunere']['cod_client']
    return _send_wb(wb, f'fisa_articole_{nume}_{valabil or id}.xlsx')


# ── F5: actualizare preturi furnizor existent (lista oficiala noua) ─────────

@pricing_bp.route('/preturi/actualizare-preturi')
def preturi_actualizare():
    an = int(request.args.get('an', datetime.date.today().year))
    return render_template('preturi_actualizare.html', an=an,
                           atribute=queries.produse_atribute_distincte())


def _rezolva_sku(cod, pe_sku, pe_baza, pe_cod_furnizor):
    if cod in pe_sku:
        return cod
    if cod + '-00' in pe_sku:
        return cod + '-00'
    if cod in pe_baza:
        return pe_baza[cod]
    return pe_cod_furnizor.get(cod)


@pricing_bp.route('/api/preturi/actualizare-preturi', methods=['POST'])
def api_actualizare_preturi():
    import re as _re
    import supplier_offer
    try:
        an = int(request.values.get('an', datetime.date.today().year))
        furnizor = (request.values.get('furnizor') or '').strip()
        if not furnizor:
            return jsonify({'error': 'Alege furnizorul.'}), 400
        curente = {r['sku']: r for r in
                   queries.furnizor_preturi_curente(furnizor, an)}
        if not curente:
            return jsonify({'error': f'Niciun articol pentru {furnizor}.'}), 400

        if request.form.get('actiune') == 'diff':
            f = request.files.get('file')
            if not f or not f.filename:
                return jsonify({'error': 'Incarca fisierul cu lista de pret.'}), 400
            mapping = {'cod': request.form.get('col_cod'),
                       'denumire': request.form.get('col_denumire')
                                   or request.form.get('col_cod'),
                       'pret': request.form.get('col_pret')}
            randuri = supplier_offer.parse_rows(
                f.filename, f.read(), mapping, request.form.get('rand_start', 2))
            pe_baza = {_re.sub(r'-\d+$', '', s): s for s in curente}
            pe_cod_furnizor = {r['cod_furnizor']: r['sku']
                               for r in curente.values() if r['cod_furnizor']}
            diff, necunoscute = [], []
            for r in randuri:
                sku = _rezolva_sku(r['cod'], curente, pe_baza, pe_cod_furnizor)
                if sku is None:
                    necunoscute.append(f"{r['cod']} | {r['denumire']}")
                    continue
                c = curente[sku]
                vechi = c['pret_achizitie_valuta']
                diff.append({
                    'sku': sku, 'descriere': c['descriere'],
                    'moneda': c['moneda'], 'pret_vechi': vechi,
                    'pret_nou': r['pret'],
                    'delta_pct': round((r['pret'] - vechi) / vechi * 100, 2)
                                 if vechi else None,
                    'pret_ultima_comanda': c['pret_ultima_comanda'],
                    'are_landing': c['landing_cost_ron'] is not None,
                })
            return jsonify({'ok': True, 'diff': diff,
                            'necunoscute': necunoscute[:50],
                            'nr_necunoscute': len(necunoscute)})

        # actiune=aplica: JSON body with the accepted rows
        d = request.get_json(silent=True) or {}
        aplicate, sarite, alerte = 0, [], []
        for li in d.get('linii', []):
            c = curente.get(li.get('sku'))
            pret_nou = float(li.get('pret_nou') or 0)
            if c is None or not pret_nou:
                continue
            if c['landing_cost_ron'] is None or c['curs_ron'] is None:
                sarite.append(f"{li['sku']}: fara landing existent - "
                              "introdu-l manual din fisa articolului")
                continue
            queries.preturi_update_landing(
                c['sku'], an, pret_nou, c['moneda'], c['curs_ron'],
                c['transport_pct'] or 0, c['taxa_vamala_pct'] or 0,
                c['alte_costuri_ron'] or 0)
            aplicate += 1
            ult = c['pret_ultima_comanda']
            if ult and abs(pret_nou - ult) / ult * 100 > 1:
                alerte.append(f"{c['sku']}: lista {pret_nou} vs ultima comanda "
                              f"{ult} ({(pret_nou - ult) / ult * 100:+.1f}%)")
        return jsonify({'ok': True, 'aplicate': aplicate,
                        'sarite': sarite[:30], 'alerte': alerte[:50]})
    except Exception as e:
        logger.exception("api_actualizare_preturi failed")
        return jsonify({'error': str(e)}), 400
