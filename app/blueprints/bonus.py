import datetime
import json
import logging
import re
from flask import Blueprint, render_template, request, jsonify
import queries
from bonus_calc import MONTHS_RO as BONUS_MONTHS_RO
from exports.excel_export import send_excel, timestamped_filename
import bonus_calc

bonus_bp = Blueprint('bonus', __name__)

logger = logging.getLogger(__name__)

# Cele 5 game pre-încărcate implicit la creare obiective noi
DEFAULT_GAME = [
    ("Basilur", 0.30), ("Toras", 0.25), ("Leonex", 0.20),
    ("Celmar", 0.15), ("Delaviuda", 0.10),
]
ALL_GAME = ['Basilur', 'Toras', 'Celmar', 'Leonex', 'Delaviuda',
            'KingsLeaf', 'Solvex', 'Tipson', 'Cosmetice', 'Organsia']


def _actual_for_kpi(kpi, db_agent, an, luna, istoric_manual, auto=None):
    """Completează 'actual' pentru un rând KPI: auto din tranzactii sau manual.

    `auto` = rezultatul cache-uit al queries.realizat_auto(...) pentru a evita
    apeluri repetate când mai multe KPI auto (vanzari/marja/clienti) sunt în listă.
    """
    tip = kpi["tip"]
    if tip in ("vanzari", "marja", "clienti"):
        if auto is None:
            auto = queries.realizat_auto(db_agent, an, luna)
        return auto[tip]
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

    # Dacă luna e închisă, citește snapshot înghețat (doar dacă e valid;
    # un snapshot gol/corupt nu trebuie să strice pagina — recalculăm live).
    if rec and rec.get("stare") == "inchis" and rec.get("lunar_data"):
        snap = json.loads(rec["lunar_data"])
        if isinstance(snap, dict) and "total_bonus" in snap:
            return snap

    istoric_manual = {}  # live: manualele neînchise vin din realizat_manual pe rând
    penalty = (rec or {}).get("penalty_pct") or 0.0
    # Cache realizatul auto (vanzari/marja/clienti) — o singură interogare per agent
    auto = queries.realizat_auto(db_agent, an, luna)
    kpis = []
    for r in rows:
        actual = _actual_for_kpi(r, db_agent, an, luna, istoric_manual, auto)
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


def build_agent_ytd(agent_key, db_agent, an, up_to_luna):
    """Agregă realizatul YTD (lunile 1..up_to_luna) pentru un agent."""
    ytd_bonus = ytd_target = sales_real = sales_target = 0.0
    luni_active = 0
    for luna in range(1, up_to_luna + 1):
        out = build_agent_month(agent_key, db_agent, an, luna)
        if not out.get('kpis'):
            continue
        luni_active += 1
        ytd_bonus += out['total_bonus']
        ytd_target += out['monthly_bonus'] or 0
        for k in out['kpis']:
            if k['tip'] == 'vanzari':
                sales_real += k['actual'] or 0
                sales_target += k['target'] or 0
    return {
        'bonus': round(ytd_bonus), 'target': round(ytd_target),
        'pct': round(ytd_bonus / ytd_target * 100, 1) if ytd_target else 0,
        'luni_active': luni_active,
        'sales_real': round(sales_real), 'sales_target': round(sales_target),
        'sales_pct': round(sales_real / sales_target * 100, 1) if sales_target else 0,
    }


@bonus_bp.route('/bonus')
def bonus():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int) or datetime.date.today().month
    agents = []
    for a in queries.bonus_agents(activ_only=True):
        out = build_agent_month(a['agent_key'], a['db_agent'], an, luna)
        out['db_agent'] = a['db_agent']
        out['ytd'] = build_agent_ytd(a['agent_key'], a['db_agent'], an, luna)
        # realizare lunară pe vânzări (pt. status vizual)
        sales = next((k for k in out['kpis'] if k['tip'] == 'vanzari'), None)
        out['sales_pct'] = round((sales['realizare'] or 0) * 100, 1) if sales else 0
        agents.append(out)
    # Totaluri pe echipă (lună + YTD)
    team = {
        'bonus':      round(sum(a['total_bonus'] for a in agents)),
        'target':     round(sum(a['monthly_bonus'] or 0 for a in agents)),
        'ytd_bonus':  round(sum(a['ytd']['bonus'] for a in agents)),
        'ytd_target': round(sum(a['ytd']['target'] for a in agents)),
    }
    return render_template('bonus.html', agents=agents, an=an, luna=luna,
                           team=team, months_ro=BONUS_MONTHS_RO)


@bonus_bp.route('/bonus/export')
def bonus_export():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int) or datetime.date.today().month
    summary, sheets = [], {}
    for a in queries.bonus_agents(activ_only=True):
        out = build_agent_month(a['agent_key'], a['db_agent'], an, luna)
        summary.append({
            'Agent': a['agent_key'], 'Bonus Lunar': out['monthly_bonus'],
            'Scor': round(out['scor'], 2), 'Bonus Realizat': round(out['total_bonus']),
            'Închis': 'Da' if out.get('inchis') else 'Nu',
        })
        sheets[a['agent_key'][:31]] = [{
            'KPI': k['tip'], 'Referință': k['referinta'] or '',
            'Target': k['target'], 'Realizat': k['actual'],
            'Realizare %': round(k['realizare'] * 100, 1),
            'Pondere %': round(k['pondere'] * 100),
            'Multiplicator': k['multiplier'], 'Bonus': round(k['bonus']),
        } for k in out['kpis']]
    sheets = {'Centralizare': summary, **sheets}
    return send_excel(sheets, timestamped_filename('bonus_echipa'))


def _py_for_row(row, py):
    """Valoarea PY same-month potrivită tipului unui rând KPI salvat."""
    tip = row["tip"]
    if tip == "vanzari":
        return py["vanzari"]
    if tip == "marja":
        return py["marja"]
    if tip == "clienti":
        return py["clienti"]
    if tip == "brand":
        return py["brand"].get(row["referinta"], 0)
    return None  # clienti_noi_gama / incasari / scriptic — fără baseline PY


def _proposed_kpis(db_agent, an, luna, growth=0.20):
    """Propune rândurile implicite cu target = PY same-month * (1+growth)."""
    py = queries.py_baseline(db_agent, an, luna)
    g = 1.0 + growth
    kpis = [
        {"tip": "vanzari", "referinta": None, "py": py["vanzari"],
         "target": round(py["vanzari"] * g), "unitate": "ron", "pondere": 0.0},
        {"tip": "marja", "referinta": None, "py": py["marja"],
         "target": round(py["marja"] * g), "unitate": "ron", "pondere": 0.0},
    ]
    for gama, pond in DEFAULT_GAME:
        base = py["brand"].get(gama, 0)
        kpis.append({"tip": "brand", "referinta": gama, "py": base,
                     "target": round(base * g), "unitate": "ron", "pondere": pond})
    return kpis


@bonus_bp.route('/bonus/obiective')
def obiective():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int) or datetime.date.today().month
    agents = []
    for a in queries.bonus_agents(activ_only=True):
        existing = queries.obiective(an, luna, a['agent_key'])
        cfg = queries.lunar_config(an, luna, a['agent_key'])
        # Creșterea efectivă: override lunar → config agent → 20% implicit
        growth = (cfg or {}).get('growth_pct') or a.get('growth_pct') or 0.20
        # Atașează baseline-ul PY și pe rândurile salvate (pt. recalc target în UI)
        if existing:
            py = queries.py_baseline(a['db_agent'], an, luna)
            for r in existing:
                r['py'] = _py_for_row(r, py)
        total_pond = sum((r['pondere'] or 0) for r in existing)
        agents.append({
            "agent_key": a['agent_key'], "db_agent": a['db_agent'],
            "has_obiective": bool(existing), "n_kpi": len(existing),
            "monthly_bonus": (cfg or {}).get('monthly_bonus'),
            "growth_pct": growth,
            "total_pondere": round(total_pond * 100),
            "kpis": existing or _proposed_kpis(a['db_agent'], an, luna, growth),
        })
    return render_template('bonus/obiective.html', agents=agents, an=an, luna=luna,
                           all_game=ALL_GAME, months_ro=BONUS_MONTHS_RO)


@bonus_bp.route('/bonus/obiective/save', methods=['POST'])
def obiective_save():
    d = request.get_json(silent=True) or {}
    try:
        an = int(d['an'])
        luna = int(d['luna'])
        key = d['agent_key']
        rec = queries.istoric_get(an, luna, key)
        if rec and rec.get('stare') == 'inchis':
            return jsonify({'ok': False,
                            'error': 'Luna este închisă — obiectivele nu mai pot fi modificate.'}), 409
        queries.save_obiective(
            an, luna, key,
            float(d['monthly_bonus']), float(d.get('growth_pct', 0.20)),
            d.get('kpis', []))
        return jsonify({'ok': True})
    except Exception as exc:
        logger.exception("obiective_save failed")
        return jsonify({'ok': False, 'error': str(exc)}), 400


@bonus_bp.route('/bonus/clienti-noi-gama')
def clienti_noi_gama():
    agent = request.args.get('agent', '')
    gama  = request.args.get('gama', '')
    an    = int(request.args.get('an', datetime.date.today().year))
    luna  = int(request.args.get('luna', datetime.date.today().month))
    rows = queries.clienti_noi_gama_list(agent, gama, an, luna)
    return render_template('bonus/clienti_noi_gama.html',
                           rows=rows, agent=agent, gama=gama, an=an, luna=luna,
                           months_ro=BONUS_MONTHS_RO)


@bonus_bp.route('/bonus/inchidere')
def inchidere():
    an   = int(request.args.get('an', datetime.date.today().year))
    luna = request.args.get('luna', type=int) or datetime.date.today().month
    agents = []
    for a in queries.bonus_agents(activ_only=True):
        out = build_agent_month(a['agent_key'], a['db_agent'], an, luna)
        manual = [k for k in out['kpis'] if k['tip'] in ('incasari', 'scriptic')]
        rec = queries.istoric_get(an, luna, a['agent_key'])
        agents.append({**out, 'db_agent': a['db_agent'],
                       'manual': manual, 'stare': (rec or {}).get('stare', 'deschis')})
    return render_template('bonus/inchidere.html', agents=agents, an=an, luna=luna,
                           months_ro=BONUS_MONTHS_RO)


@bonus_bp.route('/bonus/inchidere/lock', methods=['POST'])
def inchidere_lock():
    d = request.get_json(silent=True) or {}
    try:
        an = int(d['an'])
        luna = int(d['luna'])
        key = d['agent_key']
        rec = queries.istoric_get(an, luna, key)
        if rec and rec.get('stare') == 'inchis':
            return jsonify({'ok': False, 'error': 'Luna este deja închisă.'}), 409
        agent_cfg = next((a for a in queries.bonus_agents(activ_only=False)
                          if a['agent_key'] == key), None)
        db_agent = agent_cfg['db_agent'] if agent_cfg else key
        out = build_agent_month(key, db_agent, an, luna)
        # Realizatul manual e cheiat pe id-ul KPI (unic), nu pe tip — astfel
        # două obiective scriptice/încasări nu se suprascriu reciproc.
        manual = d.get('manual', {})
        grid = queries.payout_grid(key)
        for k in out['kpis']:
            if k['tip'] in ('incasari', 'scriptic'):
                k['actual'] = float(manual.get(str(k['id']), k.get('actual') or 0))
        recalced = bonus_calc.calc_agent_month(
            out['monthly_bonus'], float(d.get('penalty', 0.0)), out['kpis'], grid)
        recalced.update({'agent_key': key, 'monthly_bonus': out['monthly_bonus'],
                         'an': an, 'luna': luna, 'inchis': True})
        queries.istoric_lock(an, luna, key, json.dumps(recalced),
                             float(d.get('penalty', 0.0)),
                             float(d.get('grad_incasare', 1.0)), d.get('note', ''))
        return jsonify({'ok': True})
    except Exception as exc:
        logger.exception("inchidere_lock failed")
        return jsonify({'ok': False, 'error': str(exc)}), 400


@bonus_bp.route('/bonus/config')
def config():
    agents = queries.bonus_agents(activ_only=False)
    candidati = queries.field_agents_in_tranzactii()
    return render_template('bonus/config.html', agents=agents, candidati=candidati)


@bonus_bp.route('/bonus/config/agent', methods=['POST'])
def config_add_agent():
    d = request.get_json(silent=True) or {}
    try:
        agent_key = (d.get('agent_key') or '').strip()
        # Cheia e folosită în id-uri HTML și handlere JS inline — o restrângem la
        # caractere sigure (fără spații/ghilimele/diacritice) ca să evităm orice
        # breakout JS și să garantăm id-uri DOM valide.
        if not re.fullmatch(r'[A-Za-z0-9_]+', agent_key):
            return jsonify({'ok': False, 'error':
                            'Cheia agentului poate conține doar litere, cifre și _.'}), 400
        queries.add_agent(agent_key, d.get('db_agent'), d.get('tip_agent', 'field'))
        return jsonify({'ok': True})
    except Exception as exc:
        logger.exception("config_add_agent failed")
        return jsonify({'ok': False, 'error': str(exc)}), 400


@bonus_bp.route('/bonus/config/agent/<agent_key>/active', methods=['POST'])
def config_set_active(agent_key):
    d = request.get_json(silent=True) or {}
    queries.set_agent_active(agent_key, int(d.get('activ', 1)))
    return jsonify({'ok': True})


