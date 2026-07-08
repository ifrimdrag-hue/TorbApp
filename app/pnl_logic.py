"""P&L computation (relocated from pnl_app). All data access via queries.pnl."""
import queries

# Ordered display structure: (row_type, label, key). row_type: line|subtotal|pct
PNL_STRUCTURE = [
    ('line',     'Venituri marfuri',                      'Venituri marfuri'),
    ('line',     'Venituri servicii',                     'Venituri servicii'),
    ('line',     'Reduceri comerciale acordate',          'Reduceri comerciale acordate'),
    ('subtotal', 'CIFRA DE AFACERI NETA',                 'CIFRA DE AFACERI NETA'),
    ('line',     'Cost marfa',                            'Cost marfa'),
    ('line',     'Reduceri comerciale primite',           'Reduceri comerciale primite'),
    ('subtotal', 'COGS NET',                              'COGS NET'),
    ('subtotal', 'MARJA BRUTA',                           'MARJA BRUTA'),
    ('pct',      'Marja bruta %',                         'Marja bruta %'),
    ('line',     'Consumabile / utilitati / combustibil', 'Consumabile / utilitati / combustibil'),
    ('line',     'Servicii terti / logistica / marketing', 'Servicii terti / logistica / marketing'),
    ('line',     'Cheltuieli personal',                   'Cheltuieli personal'),
    ('line',     'Impozite si taxe',                      'Impozite si taxe'),
    ('line',     'Alte cheltuieli exploatare',            'Alte cheltuieli exploatare'),
    ('line',     'Alte venituri exploatare',              'Alte venituri exploatare'),
    ('subtotal', 'EBITDA',                                'EBITDA'),
    ('pct',      'EBITDA %',                              'EBITDA %'),
    ('line',     'Amortizare',                            'Amortizare'),
    ('subtotal', 'EBIT',                                  'EBIT'),
    ('line',     'Venituri financiare',                   'Venituri financiare'),
    ('line',     'Cheltuieli financiare',                 'Cheltuieli financiare'),
    ('subtotal', 'PROFIT INAINTE DE IMPOZIT',             'PROFIT INAINTE DE IMPOZIT'),
    ('line',     'Impozit profit',                        'Impozit profit'),
    ('subtotal', 'PROFIT NET',                            'PROFIT NET'),
    ('pct',      'Profit net %',                          'Profit net %'),
]


def _entity_monthly(entitate, an, luna, mapping):
    """{cont: monthly_amount} from the month's own turnovers: rulld for expense
    accounts (mapping semn < 0), rullc for revenue accounts (semn > 0). No
    prior-month dependency, so any subset of months imports correctly."""
    raw = queries.pnl_monthly_raw(entitate, an, luna)
    out = {}
    for cont, (rulld, rullc) in raw.items():
        semn = mapping[cont][1] if cont in mapping else 1
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
        if cont not in mapping:
            continue
        pnl_line, semn = mapping[cont]
        lines[pnl_line] = lines.get(pnl_line, 0.0) + semn * amount

    ca_neta = (lines.get('Venituri marfuri', 0)
               + lines.get('Venituri servicii', 0)
               + lines.get('Reduceri comerciale acordate', 0))
    cogs_net = (lines.get('Cost marfa', 0)
                + lines.get('Reduceri comerciale primite', 0))
    marja_bruta = ca_neta + cogs_net
    opex = (lines.get('Consumabile / utilitati / combustibil', 0)
            + lines.get('Servicii terti / logistica / marketing', 0)
            + lines.get('Cheltuieli personal', 0)
            + lines.get('Impozite si taxe', 0)
            + lines.get('Alte cheltuieli exploatare', 0)
            + lines.get('Alte venituri exploatare', 0))
    ebitda = marja_bruta + opex
    ebit = ebitda + lines.get('Amortizare', 0)
    fin = lines.get('Venituri financiare', 0) + lines.get('Cheltuieli financiare', 0)
    pbi = ebit + fin
    profit_net = pbi + lines.get('Impozit profit', 0)

    lines['CIFRA DE AFACERI NETA'] = ca_neta
    lines['COGS NET'] = cogs_net
    lines['MARJA BRUTA'] = marja_bruta
    lines['Marja bruta %'] = (marja_bruta / ca_neta * 100) if ca_neta else 0.0
    lines['EBITDA'] = ebitda
    lines['EBITDA %'] = (ebitda / ca_neta * 100) if ca_neta else 0.0
    lines['EBIT'] = ebit
    lines['PROFIT INAINTE DE IMPOZIT'] = pbi
    lines['PROFIT NET'] = profit_net
    lines['Profit net %'] = (profit_net / ca_neta * 100) if ca_neta else 0.0
    return lines


def compute_pnl_month(entitate, an, luna):
    """Full P&L dict for one entity+month from own-month turnovers. Grup sums both."""
    mapping = queries.pnl_mapping()
    return _build_lines(_raw_monthly(entitate, an, luna, mapping), mapping)


def compute_pnl_month_warnings(entitate, an, luna):
    """Cross-check: {pnl_line: {'monthly','delta'}} for lines where the own-month
    figure diverges from the Δrulcd figure by >= 0.05. Only when the prior month
    exists (else Δrulcd is meaningless). A divergence flags a source-data anomaly
    (the accountant's monthly turnovers do not cumulate) — surfaced as ⚠ in the grid."""
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
    """Compare computed net-profit YTD (cumulative rulcd × semn) with the 121
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
    pn = sum(mapping[c][1] * v for c, v in cum.items() if c in mapping)
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
