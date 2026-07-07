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


def _raw_monthly(entitate, an, luna):
    """{cont: monthly_amount} = rulcd_current - rulcd_prior (raw delta)."""
    cur = queries.pnl_rulcd(entitate, an, luna)
    prior = queries.pnl_rulcd(entitate, an, luna - 1) if luna > 1 else {}
    return {cont: cur[cont] - prior.get(cont, 0.0) for cont in cur}


def compute_pnl_month(entitate, an, luna):
    """Full P&L dict for one entity+month. entitate='grup' sums torb+tobra."""
    mapping = queries.pnl_mapping()
    if entitate == 'grup':
        torb = _raw_monthly('torb', an, luna)
        tobra = _raw_monthly('tobra', an, luna)
        raw = {c: torb.get(c, 0) + tobra.get(c, 0) for c in set(torb) | set(tobra)}
    else:
        raw = _raw_monthly(entitate, an, luna)

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


def compute_pnl_year(entitate, an):
    """{luna: pnl_dict} for all available months."""
    luni = queries.pnl_available_months(an, entitate)
    return {luna: compute_pnl_month(entitate, an, luna) for luna in luni}


def compute_ytd(entitate, an, through_luna):
    """Sum Jan..through_luna. % lines recomputed from sums."""
    months = compute_pnl_year(entitate, an)
    totals = {}
    pct_keys = {'Marja bruta %', 'EBITDA %', 'Profit net %'}
    for luna in range(1, through_luna + 1):
        for k, v in months.get(luna, {}).items():
            if k not in pct_keys:
                totals[k] = totals.get(k, 0.0) + v
    ca = totals.get('CIFRA DE AFACERI NETA', 0)
    totals['Marja bruta %'] = (totals.get('MARJA BRUTA', 0) / ca * 100) if ca else 0.0
    totals['EBITDA %'] = (totals.get('EBITDA', 0) / ca * 100) if ca else 0.0
    totals['Profit net %'] = (totals.get('PROFIT NET', 0) / ca * 100) if ca else 0.0
    return totals


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
