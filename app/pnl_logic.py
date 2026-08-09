"""P&L computation (relocated from pnl_app). All data access via queries.pnl."""
import queries

# Ordered display structure: (row_type, label, key). row_type: line|subtotal|pct
# `key` is a stable identifier stored in pnl_mapping_conturi.pnl_line and
# pnl_config.pnl_line; `label` is UI text and may change without a migration.
PNL_STRUCTURE = [
    ('line',     'Venituri mărfuri',                'venituri_marfa'),
    ('line',     'Venituri servicii și alte activități', 'venituri_servicii'),
    ('line',     'Reduceri comerciale acordate',     'reduceri_acordate'),
    ('subtotal', 'CIFRA DE AFACERI NETĂ',            'ca_neta'),
    ('line',     'Cost marfă',                       'cost_marfa'),
    ('line',     'Reduceri comerciale primite',      'reduceri_primite'),
    ('subtotal', 'MARJA BRUTĂ',                      'marja_bruta'),
    ('pct',      'Marjă brută %',                    'marja_bruta_pct'),
    ('line',     'Cheltuieli personal',              'ch_personal'),
    ('line',     'Transport și logistică',           'transport_logistica'),
    ('line',     'Marketing și protocol',            'marketing_comercial'),
    ('line',     'Chirii și utilități',              'chirii_utilitati'),
    ('line',     'Servicii terți și administrativ',  'servicii_terti'),
    ('line',     'Consumabile și obiecte de inventar', 'consumabile'),
    ('line',     'Impozite și taxe',                 'impozite_taxe'),
    ('line',     'Alte cheltuieli exploatare',       'alte_ch_exploatare'),
    ('line',     'Alte venituri exploatare',         'alte_ven_exploatare'),
    ('subtotal', 'EBITDA',                           'ebitda'),
    ('pct',      'EBITDA %',                         'ebitda_pct'),
    ('line',     'Amortizare și provizioane',        'amortizare_provizioane'),
    ('subtotal', 'EBIT',                             'ebit'),
    ('line',     'Venituri financiare',              'venituri_financiare'),
    ('line',     'Cheltuieli financiare',            'cheltuieli_financiare'),
    ('subtotal', 'PROFIT ÎNAINTE DE IMPOZIT',        'profit_brut'),
    ('line',     'Impozit pe profit / venit',        'impozit'),
    ('subtotal', 'PROFIT NET',                       'profit_net'),
    ('pct',      'Profit net %',                     'profit_net_pct'),
]

PNL_LABELS = {key: label for _t, label, key in PNL_STRUCTURE}
PNL_ROW_TYPES = {key: row_type for row_type, _lbl, key in PNL_STRUCTURE}

# Lines summed into EBITDA on top of the gross margin (operating block).
_OPEX_KEYS = ('ch_personal', 'transport_logistica', 'marketing_comercial',
              'chirii_utilitati', 'servicii_terti', 'consumabile',
              'impozite_taxe', 'alte_ch_exploatare', 'alte_ven_exploatare')

MIN_PREFIX_LEN = 3


def resolve_cont(cont, mapping):
    """(pnl_line, semn) for an account: exact match first, then the longest
    mapped prefix of at least MIN_PREFIX_LEN chars, so analytic accounts follow
    their synthetic parent (6221 -> 622). None when nothing matches."""
    if cont in mapping:
        return mapping[cont]
    for n in range(len(cont) - 1, MIN_PREFIX_LEN - 1, -1):
        parent = cont[:n]
        if parent in mapping:
            return mapping[parent]
    return None


def _entity_monthly(entitate, an, luna, mapping):
    """{cont: monthly_amount} from the month's own turnovers: rulld for expense
    accounts (mapping semn < 0), rullc for revenue accounts (semn > 0). No
    prior-month dependency, so any subset of months imports correctly."""
    raw = queries.pnl_monthly_raw(entitate, an, luna)
    out = {}
    for cont, (rulld, rullc) in raw.items():
        resolved = resolve_cont(cont, mapping)
        semn = resolved[1] if resolved else 1
        out[cont] = rulld if semn < 0 else rullc
    return out


def _raw_monthly(entitate, an, luna, mapping=None):
    """{cont: monthly_amount} from own-month turnovers. Grup sums torb+tobra."""
    if mapping is None:
        mapping = queries.pnl_mapping()
    if entitate == 'grup':
        torb = _entity_monthly('torb', an, luna, mapping)
        tobra = _entity_monthly('tobra', an, luna, mapping)
        return {c: torb.get(c, 0) + tobra.get(c, 0) for c in set(torb) | set(tobra)}
    return _entity_monthly(entitate, an, luna, mapping)


def _cumulative(entitate, an, luna):
    """{cont: rulcd} cumulative debit turnover at this month. Grup sums both.
    This is the authoritative YTD figure that reconciles with account 121."""
    if entitate == 'grup':
        torb = queries.pnl_rulcd('torb', an, luna)
        tobra = queries.pnl_rulcd('tobra', an, luna)
        return {c: torb.get(c, 0) + tobra.get(c, 0) for c in set(torb) | set(tobra)}
    return queries.pnl_rulcd(entitate, an, luna)


def _build_lines(raw, mapping):
    """Assemble the full P&L dict (lines + subtotals + % lines) from {cont: amount}."""
    lines = {}
    for cont, amount in raw.items():
        resolved = resolve_cont(cont, mapping)
        if resolved is None:
            continue
        pnl_line, semn = resolved
        lines[pnl_line] = lines.get(pnl_line, 0.0) + semn * amount

    ca_neta = (lines.get('venituri_marfa', 0)
               + lines.get('venituri_servicii', 0)
               + lines.get('reduceri_acordate', 0))
    marja_bruta = (ca_neta
                   + lines.get('cost_marfa', 0)
                   + lines.get('reduceri_primite', 0))
    ebitda = marja_bruta + sum(lines.get(k, 0) for k in _OPEX_KEYS)
    ebit = ebitda + lines.get('amortizare_provizioane', 0)
    profit_brut = (ebit
                   + lines.get('venituri_financiare', 0)
                   + lines.get('cheltuieli_financiare', 0))
    profit_net = profit_brut + lines.get('impozit', 0)

    lines['ca_neta'] = ca_neta
    lines['marja_bruta'] = marja_bruta
    lines['marja_bruta_pct'] = (marja_bruta / ca_neta * 100) if ca_neta else 0.0
    lines['ebitda'] = ebitda
    lines['ebitda_pct'] = (ebitda / ca_neta * 100) if ca_neta else 0.0
    lines['ebit'] = ebit
    lines['profit_brut'] = profit_brut
    lines['profit_net'] = profit_net
    lines['profit_net_pct'] = (profit_net / ca_neta * 100) if ca_neta else 0.0
    return lines


def compute_pnl_month(entitate, an, luna):
    """Full P&L dict for one entity+month from own-month turnovers. Grup sums both."""
    mapping = queries.pnl_mapping()
    return _build_lines(_raw_monthly(entitate, an, luna, mapping), mapping)


def compute_pnl_month_warnings(entitate, an, luna):
    """Cross-check: {pnl_line: {'monthly','delta'}} for lines where the own-month
    figure diverges from the Delta-rulcd figure by >= 0.05. Only when the prior
    month exists (else Delta-rulcd is meaningless). A divergence flags a
    source-data anomaly (the accountant's monthly turnovers do not cumulate) —
    surfaced as a warning icon in the grid."""
    if luna <= 1 or not queries.pnl_available_months(an, entitate) \
            or (luna - 1) not in queries.pnl_available_months(an, entitate):
        return {}
    mapping = queries.pnl_mapping()
    own = _build_lines(_raw_monthly(entitate, an, luna, mapping), mapping)
    cur = _cumulative(entitate, an, luna)
    prior = _cumulative(entitate, an, luna - 1)
    delta = {c: cur.get(c, 0) - prior.get(c, 0) for c in set(cur) | set(prior)}
    delta_lines = _build_lines(delta, mapping)
    warnings = {}
    for _t, _lbl, key in PNL_STRUCTURE:
        if _t != 'line':
            continue
        d = abs(own.get(key, 0) - delta_lines.get(key, 0))
        if d >= 0.05:
            warnings[key] = {'monthly': own.get(key, 0), 'delta': delta_lines.get(key, 0)}
    return warnings


def compute_pnl_year(entitate, an):
    """{luna: pnl_dict} for all available months."""
    luni = queries.pnl_available_months(an, entitate)
    return {luna: compute_pnl_month(entitate, an, luna) for luna in luni}


def compute_ytd(entitate, an, through_luna):
    """YTD P&L from cumulative rulcd at through_luna (the figure that reconciles
    with account 121). Self-sufficient: needs only the through-month's balance,
    not every intermediate month, and never mislabels cumulative as monthly."""
    mapping = queries.pnl_mapping()
    return _build_lines(_cumulative(entitate, an, through_luna), mapping)


def reconciliere_121(entitate, an, luna):
    """Compare computed net-profit YTD (cumulative rulcd x semn) with the 121
    balance carried in that entity+month. Returns {'pn','sold','diff','ok'} or
    None when 121 is absent. Grup sums both entities' 121."""
    if entitate == 'grup':
        t = reconciliere_121('torb', an, luna)
        b = reconciliere_121('tobra', an, luna)
        if t is None or b is None:
            return None
        pn = t['pn'] + b['pn']
        sold = t['sold'] + b['sold']
        diff = round(pn - sold, 2)
        return {'pn': round(pn, 2), 'sold': round(sold, 2),
                'diff': diff, 'ok': abs(diff) < 0.05}
    mapping = queries.pnl_mapping()
    cum = queries.pnl_rulcd(entitate, an, luna)
    pn = 0.0
    for cont, val in cum.items():
        resolved = resolve_cont(cont, mapping)
        if resolved is not None:
            pn += resolved[1] * val
    sold_121 = queries.pnl_sold_cont(entitate, an, luna, '121')
    if sold_121 is None:
        return None
    sold = sold_121
    diff = round(pn - sold, 2)
    return {'pn': round(pn, 2), 'sold': round(sold, 2),
            'diff': diff, 'ok': abs(diff) < 0.05}


def available_years():
    return queries.pnl_available_years()


def load_alarm_config():
    return queries.pnl_alarm_config()


def compute_alarm(current, prior, pct_value, cfg):
    """{'delta_severity': ..., 'prag_severity': ...} — ok|warning|error|success|None."""
    result = {'delta_severity': None, 'prag_severity': None}

    dw = cfg.get('alarma_delta_warn')
    de = cfg.get('alarma_delta_err')
    if dw is not None and prior and prior != 0 and current is not None:
        delta = (current - prior) / abs(prior)
        directie = cfg.get('directie', 'sus_bine')
        if directie == 'sus_bine':
            if de is not None and delta <= de:
                result['delta_severity'] = 'error'
            elif delta <= dw:
                result['delta_severity'] = 'warning'
            elif delta >= 0.05:
                result['delta_severity'] = 'success'
            else:
                result['delta_severity'] = 'ok'
        else:  # jos_bine (costs — increase is bad)
            if de is not None and delta >= de:
                result['delta_severity'] = 'error'
            elif delta >= dw:
                result['delta_severity'] = 'warning'
            elif delta <= -0.05:
                result['delta_severity'] = 'success'
            else:
                result['delta_severity'] = 'ok'

    pw = cfg.get('alarma_prag_warn')
    pe = cfg.get('alarma_prag_err')
    if pw is not None and pct_value is not None:
        pct = pct_value / 100 if pct_value > 1 else pct_value
        if pe is not None and pct <= pe:
            result['prag_severity'] = 'error'
        elif pct <= pw:
            result['prag_severity'] = 'warning'
        else:
            result['prag_severity'] = 'ok'

    return result


def compute_trend_alarm(entitate, pnl_line, an, luna, n_luni=3):
    """True if pnl_line deteriorated n_luni consecutive months."""
    if luna < n_luni:
        return False
    values = []
    for m in range(luna - n_luni + 1, luna + 1):
        values.append(compute_pnl_month(entitate, an, m).get(pnl_line, 0.0))
    return all(values[i] < values[i - 1] for i in range(1, len(values)))
