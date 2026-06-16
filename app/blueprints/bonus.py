import datetime
import json
import logging
from flask import Blueprint, render_template, request, jsonify
import queries
from bonus_calc import (
    PRESETS,
    SIM_MONTHS,
    MONTHS_RO as BONUS_MONTHS_RO,
    STRATEGIC_BRANDS,
    STRATEGIC_WEIGHTS_DEFAULT,
    simulate,
)
from exports.excel_export import send_excel, timestamped_filename
import bonus_calc

bonus_bp = Blueprint('bonus', __name__)

logger = logging.getLogger(__name__)


def _actual_for_kpi(kpi, db_agent, an, luna, istoric_manual):
    """Completează 'actual' pentru un rând KPI: auto din tranzactii sau manual."""
    tip = kpi["tip"]
    if tip == "vanzari":
        return queries.realizat_auto(db_agent, an, luna)["vanzari"]
    if tip == "marja":
        return queries.realizat_auto(db_agent, an, luna)["marja"]
    if tip == "clienti":
        return queries.realizat_auto(db_agent, an, luna)["clienti"]
    if tip == "brand":
        return queries.realizat_brand(db_agent, kpi["referinta"], an, luna)
    if tip == "clienti_noi_gama":
        return queries.clienti_noi_gama_count(db_agent, kpi["referinta"], an, luna)
    # incasari / scriptic → manual (din istoric înghețat sau realizat_manual)
    return istoric_manual.get(str(kpi.get("id")), kpi.get("realizat_manual") or 0.0)


def build_agent_month(agent_key, db_agent, an, luna):
    """Agregă obiectivele + realizatul + grila → rezultat per agent/lună."""
    cfg = queries.lunar_config(an, luna, agent_key) or {"monthly_bonus": 0, "growth_pct": 0.20}
    rows = queries.obiective(an, luna, agent_key)
    grid = queries.payout_grid(agent_key)
    rec = queries.istoric_get(an, luna, agent_key)

    # Dacă luna e închisă, citește snapshot înghețat
    if rec and rec.get("stare") == "inchis" and rec.get("lunar_data"):
        return json.loads(rec["lunar_data"])

    istoric_manual = {}  # live: manualele neînchise vin din realizat_manual pe rând
    penalty = (rec or {}).get("penalty_pct") or 0.0
    kpis = []
    for r in rows:
        actual = _actual_for_kpi(r, db_agent, an, luna, istoric_manual)
        kpis.append({
            "tip": r["tip"], "referinta": r["referinta"],
            "target": r["target"] or 0.0, "unitate": r["unitate"],
            "pondere": r["pondere"] or 0.0, "actual": actual,
            "id": r["id"],
        })
    out = bonus_calc.calc_agent_month(cfg["monthly_bonus"], penalty, kpis, grid)
    out["agent_key"] = agent_key
    out["monthly_bonus"] = cfg["monthly_bonus"]
    out["an"] = an
    out["luna"] = luna
    out["inchis"] = bool(rec and rec.get("stare") == "inchis")
    return out


def _build_agent_months_data(db_agent, preset):
    """Build months_data list for simulate() from DB actuals."""
    py = queries.prior_year()
    cy = queries.current_year()
    all_rows = queries.agent_monthly_all_years(db_agent)
    months_py, months_cy = {}, {}
    for r in all_rows:
        d = {'val_neta': r['val_neta'], 'marja_bruta': r['marja_bruta']}
        if r['an'] == py:
            months_py[int(r['luna'])] = d
        elif r['an'] == cy:
            months_cy[int(r['luna'])] = d

    def _brand_monthly(an):
        result = {}
        for r in queries.agent_brand_monthly(db_agent, an):
            m = int(r['luna'])
            result.setdefault(m, {})[r['furnizor']] = r['val_neta']
        return result

    brands_py = _brand_monthly(py)
    brands_cy = _brand_monthly(cy)
    growth = preset['growth_pct']

    months_data = []
    for m in SIM_MONTHS:
        base   = months_py.get(m, {})
        actual = months_cy.get(m, {})
        b25    = brands_py.get(m, {})
        b26    = brands_cy.get(m, {})

        weighted_att, total_w = 0.0, 0.0
        for b in STRATEGIC_BRANDS:
            base_b   = b25.get(b, 0) or 0
            actual_b = b26.get(b, 0) or 0
            target_b = base_b * (1 + growth)
            att_b    = (actual_b / target_b) if target_b > 0 else 0.0
            w = STRATEGIC_WEIGHTS_DEFAULT[b]
            weighted_att += att_b * w
            total_w      += w
        strategic_att = (weighted_att / total_w) if total_w > 0 else 0.0

        months_data.append({
            'base_sales':      base.get('val_neta', 0) or 0,
            'actual_sales':    actual.get('val_neta', 0) or 0,
            'base_margin':     base.get('marja_bruta', 0) or 0,
            'actual_margin':   actual.get('marja_bruta', 0) or 0,
            'strategic_att':   strategic_att,
            'collection_factor': 1.0,
        })
    return months_data


@bonus_bp.route('/bonus')
def bonus():
    an      = int(request.args.get('an', datetime.date.today().year))
    luna    = request.args.get('luna', type=int)
    py_yr   = an - 1
    cy_yr   = an
    max_luna = None if luna else queries.max_luna_for_year(cy_yr)

    def _in_period(m):
        return int(m) == luna if luna else (max_luna is None or int(m) <= max_luna)

    agents_data = []
    for name, preset in PRESETS.items():
        db_agent = preset.get('db_agent')
        params = {k: v for k, v in preset.items() if k != 'db_agent'}
        if db_agent:
            months_data = _build_agent_months_data(db_agent, preset)
        else:
            months_data = [{'base_sales': 0, 'actual_sales': 0, 'base_margin': 0,
                            'actual_margin': 0, 'strategic_att': 0, 'collection_factor': 1.0}
                           for _ in SIM_MONTHS]
        result = simulate(params, months_data)

        # Per-brand strategic data filtered by selected period
        brand_py, brand_cy = {}, {}
        if db_agent:
            for r in queries.agent_brand_monthly(db_agent, py_yr):
                if _in_period(r['luna']):
                    brand_py[r['furnizor']] = brand_py.get(r['furnizor'], 0) + (r['val_neta'] or 0)
            for r in queries.agent_brand_monthly(db_agent, cy_yr):
                if _in_period(r['luna']):
                    brand_cy[r['furnizor']] = brand_cy.get(r['furnizor'], 0) + (r['val_neta'] or 0)

        growth = preset['growth_pct']
        strategic_period = []
        w_att, total_w = 0.0, 0.0
        for b in STRATEGIC_BRANDS:
            base   = brand_py.get(b, 0) or 0
            actual = brand_cy.get(b, 0) or 0
            target = round(base * (1 + growth))
            att    = (actual / target) if target > 0 else 0.0
            w      = STRATEGIC_WEIGHTS_DEFAULT[b]
            w_att += att * w
            total_w += w
            strategic_period.append({
                'brand': b, 'weight': int(w * 100),
                'base': round(base), 'target': target,
                'actual': round(actual), 'att': round(att * 100, 1),
            })
        period_strategic = round((w_att / total_w * 100) if total_w else 0, 1)

        # Period KPIs from monthly simulation results
        period_months = [m for m in result['months']
                         if (luna and m['month'] == luna) or
                            (not luna and (max_luna is None or m['month'] <= max_luna))]
        p_target_s = sum(m['target_sales'] for m in period_months)
        p_actual_s = sum(m['sales_att'] * m['target_sales'] for m in period_months)
        p_target_m = sum(m['target_margin'] for m in period_months)
        p_actual_m = sum(m['margin_att'] * m['target_margin'] for m in period_months)
        period_bonus  = round(sum(m['total_bonus'] for m in period_months), 0)
        months_w_data = len([m for m in period_months if m['target_sales'] > 0 or m['target_margin'] > 0])
        period_target = preset['monthly_bonus'] * months_w_data
        period_pct    = round(period_bonus / period_target * 100, 1) if period_target else 0

        agents_data.append({
            'name':             name,
            'db_agent':         db_agent or '—',
            'preset':           preset,
            'result':           result,
            'months':           result['months'],
            'strategic_period': strategic_period,
            'period_strategic': period_strategic,
            'period_sales_att': round(p_actual_s / p_target_s * 100, 1) if p_target_s else 0,
            'period_margin_att':round(p_actual_m / p_target_m * 100, 1) if p_target_m else 0,
            'period_bonus':     period_bonus,
            'period_target':    period_target,
            'period_pct':       period_pct,
            'period_active':    months_w_data,
        })
    return render_template('bonus.html', agents=agents_data, months_ro=BONUS_MONTHS_RO,
                           an=an, luna=luna, max_luna=max_luna)


@bonus_bp.route('/bonus/simulator')
def bonus_simulator():
    presets_json = json.dumps({
        name: {k: v for k, v in p.items() if k != 'db_agent'}
        for name, p in PRESETS.items()
    })
    sim_months = [{'num': m, 'label': BONUS_MONTHS_RO[m - 1]} for m in SIM_MONTHS]
    strat_brands = [
        {'name': b, 'weight': STRATEGIC_WEIGHTS_DEFAULT[b]}
        for b in STRATEGIC_BRANDS
    ]
    return render_template(
        'bonus_simulator.html',
        presets=PRESETS,
        presets_json=presets_json,
        sim_months=sim_months,
        strat_brands=strat_brands,
        strat_brands_json=json.dumps(STRATEGIC_BRANDS),
        strat_weights_json=json.dumps(STRATEGIC_WEIGHTS_DEFAULT),
    )


@bonus_bp.route('/api/bonus/agent-data/<name>')
def api_bonus_agent_data(name):
    if name not in PRESETS:
        return jsonify({'error': 'Preset necunoscut'}), 404
    py = queries.prior_year()
    cy = queries.current_year()
    db_agent = PRESETS[name].get('db_agent')
    if not db_agent:
        return jsonify({'py': py, 'cy': cy,
                        'months_py': {}, 'months_cy': {},
                        'brands_py': {}, 'brands_cy': {}})

    # Monthly sales+margin for both years
    all_rows = queries.agent_monthly_all_years(db_agent)
    months_py, months_cy = {}, {}
    for r in all_rows:
        d = {'val_neta': r['val_neta'], 'marja_bruta': r['marja_bruta']}
        if r['an'] == py:
            months_py[int(r['luna'])] = d
        elif r['an'] == cy:
            months_cy[int(r['luna'])] = d

    # Monthly brand strategic data — {month: {brand: val}}
    def _brand_monthly(an):
        result = {}
        for r in queries.agent_brand_monthly(db_agent, an):
            m = int(r['luna'])
            result.setdefault(m, {})[r['furnizor']] = r['val_neta']
        return result

    return jsonify({
        'py': py, 'cy': cy,
        'months_py': months_py,
        'months_cy': months_cy,
        'brands_py': _brand_monthly(py),
        'brands_cy': _brand_monthly(cy),
    })


@bonus_bp.route('/api/bonus/simulate', methods=['POST'])
def api_bonus_simulate():
    data = request.get_json(silent=True) or {}
    try:
        params = {
            'monthly_bonus': float(data.get('monthly_bonus', 0)),
            'growth_pct':    float(data.get('growth_pct', 0.20)),
            'w_sales':       float(data.get('w_sales', 0.45)),
            'w_margin':      float(data.get('w_margin', 0.25)),
            'w_strategic':   float(data.get('w_strategic', 0.30)),
            'gate_sales':    float(data.get('gate_sales', 0.85)),
            'gate_margin':   float(data.get('gate_margin', 0.85)),
            'penalty':       float(data.get('penalty', 0.0)),
        }
        months_data = data.get('months', [])
        result = simulate(params, months_data)
        return jsonify(result)
    except Exception as exc:
        logger.exception("bonus simulate failed")
        return jsonify({'error': str(exc)}), 400


@bonus_bp.route('/bonus/export')
def bonus_export():
    summary_rows = []
    sheets = {}
    for name, preset in PRESETS.items():
        db_agent = preset.get('db_agent')
        params   = {k: v for k, v in preset.items() if k != 'db_agent'}
        months_data = _build_agent_months_data(db_agent, preset) if db_agent else [
            {'base_sales': 0, 'actual_sales': 0, 'base_margin': 0,
             'actual_margin': 0, 'strategic_att': 0, 'collection_factor': 1.0}
            for _ in SIM_MONTHS
        ]
        result = simulate(params, months_data)
        active = sum(1 for m in result['months'] if m['total_bonus'] > 0)
        summary_rows.append({
            'Agent':              name,
            'DB Agent':           db_agent or '—',
            'Bonus Lunar Target': preset['monthly_bonus'],
            'Bonus Anual Target': result['annual_target'],
            'Bonus Realizat YTD': round(result['annual_bonus'], 0),
            'Realizare %':        result['payout_pct'],
            'Luni cu bonus':      active,
        })
        month_rows = []
        for m in result['months']:
            month_rows.append({
                'Luna':               BONUS_MONTHS_RO[m['month'] - 1],
                'Target Vanzari':     m['target_sales'],
                'Target Marja':       m['target_margin'],
                'Realizare Vanzari %': round(m['sales_att'] * 100, 1),
                'Realizare Marja %':   round(m['margin_att'] * 100, 1),
                'Strategic %':         round(m['strategic_att'] * 100, 1),
                'Gate Strategic':      'Da' if m['gate_strategic_ok'] else 'Nu',
                'Bonus Vanzari':       m['sales_bonus'],
                'Bonus Marja':         m['margin_bonus'],
                'Bonus Strategic':     m['strategic_bonus'],
                'Total Bonus':         m['total_bonus'],
            })
        sheets[name[:31]] = month_rows
    sheets = {'Centralizare': summary_rows, **sheets}
    return send_excel(sheets, timestamped_filename('bonus_echipa'))


@bonus_bp.route('/bonus/simulator/export', methods=['POST'])
def bonus_simulator_export():
    data   = request.get_json(silent=True) or {}
    agent  = data.get('agent', 'Manual')
    months = data.get('months', [])
    headers = [
        'Luna', 'Baza Vanzari', 'Target Vanzari', 'Actual Vanzari', 'Realizare Vanzari %',
        'Baza Marja', 'Target Marja', 'Actual Marja', 'Realizare Marja %',
        'Strategic %', 'Gate OK', 'Bonus Vanzari', 'Bonus Marja', 'Bonus Strategic', 'Total Bonus',
    ]
    rows = [{
        'Luna':                  m.get('luna', ''),
        'Baza Vanzari':          m.get('baza_vanzari', 0),
        'Target Vanzari':        m.get('target_vanzari', 0),
        'Actual Vanzari':        m.get('actual_vanzari', 0),
        'Realizare Vanzari %':   m.get('realizare_vanzari_pct', 0),
        'Baza Marja':            m.get('baza_marja', 0),
        'Target Marja':          m.get('target_marja', 0),
        'Actual Marja':          m.get('actual_marja', 0),
        'Realizare Marja %':     m.get('realizare_marja_pct', 0),
        'Strategic %':           m.get('strategic_pct', 0),
        'Gate OK':               'Da' if m.get('gate_ok') else 'Nu',
        'Bonus Vanzari':         m.get('bonus_vanzari', 0),
        'Bonus Marja':           m.get('bonus_marja', 0),
        'Bonus Strategic':       m.get('bonus_strategic', 0),
        'Total Bonus':           m.get('total_bonus', 0),
    } for m in months]
    return send_excel(
        {'Simulator ' + agent: {'rows': rows, 'headers': headers}},
        timestamped_filename(f'bonus_{agent}'),
    )
