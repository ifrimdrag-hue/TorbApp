"""Context builders for the list and report page exports.

`exports.entities` resolves one identifier; these resolve a set of filters.
Both emit the same context dict (see exports.context), so one Excel route and
one PPT route serve every page and the two formats cannot drift apart.

Unlike the entity builders, an empty result is not a 404 here: a filter that
matches nothing is a valid answer and yields an empty sheet.
"""
import queries
from exports.context import SHEET_ROW_LIMIT, pct, period_label, table
from exports.ppt_export import fmt_pct, fmt_ron

# One table filling the slide: left inset, usable width, in inches.
FULL_WIDTH = (0.3, 12.7)


def _totals(rows):
    """(val_neta, marja_bruta, marja_neta) summed over already-filtered rows."""
    return (
        sum((r.get('val_neta') or 0) for r in rows),
        sum((r.get('marja_bruta') or 0) for r in rows),
        sum((r.get('marja_neta') or 0) for r in rows),
    )


def _team(an, luna, max_luna, filters):
    rows_cy = queries.team_table(an, luna=luna, max_luna=max_luna)
    rows_py = queries.team_table(an - 1, luna=luna, max_luna=max_luna)
    vn, mb, mn = _totals(rows_cy)
    left, width = FULL_WIDTH

    return {
        'nav': 'team',
        'title': f"Echipă {an}",
        'filename_base': f'echipa_{an}',
        'cards': [
            ("Val. Netă", fmt_ron(vn)),
            ("Marjă Brută", f"{fmt_ron(mb)} / {fmt_pct(pct(mb, vn))}"),
            ("Marjă Netă", f"{fmt_ron(mn)} / {fmt_pct(pct(mn, vn))}"),
            ("Nr. Agenți", str(len(rows_cy))),
        ],
        'tables': [
            table(f"Echipa {an}", left, width, rows_cy, lambda r: {
                "Agent": (r.get('agent') or "—")[:24],
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB RON": fmt_ron(r.get('marja_bruta')),
                "MB%": fmt_pct(r.get('marja_pct')),
                "MN RON": fmt_ron(r.get('marja_neta')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
                "Clienți": str(r.get('clienti_activi') or 0),
            }),
        ],
        'extra_tables': [],
        'sheets': {
            f'Echipa {an}': rows_cy,
            f'Echipa {an - 1}': rows_py,
        },
        'trend': None,
    }


def _clients(an, luna, max_luna, filters):
    # The page caps at clients_list's default limit for render speed; the
    # workbook is the full-data artifact, so it asks for everything.
    rows = queries.clients_list(
        an,
        search=filters.get('q') or None,
        agent=filters.get('agent') or None,
        churn=filters.get('churn') or None,
        brand=filters.get('brand') or None,
        luna=luna, max_luna=max_luna, limit=SHEET_ROW_LIMIT,
    )
    vn, mb, mn = _totals(rows)
    left, width = FULL_WIDTH

    return {
        'nav': 'clients',
        'title': f"Clienți {an}",
        'filename_base': f'clienti_{an}',
        'cards': [
            ("Val. Netă", fmt_ron(vn)),
            ("Marjă Brută %", fmt_pct(pct(mb, vn))),
            ("Marjă Netă", f"{fmt_ron(mn)} / {fmt_pct(pct(mn, vn))}"),
            ("Nr. Clienți", str(len(rows))),
        ],
        'tables': [
            table(f"Clienți {an}", left, width, rows, lambda r: {
                "Client": (r.get('client') or "—")[:26],
                "Agent": (r.get('agent') or "—")[:14],
                "Val. Netă": fmt_ron(r.get('val_neta')),
                "MB%": fmt_pct(r.get('marja_bruta_pct')),
                "MN RON": fmt_ron(r.get('marja_neta')),
                "MN%": fmt_pct(r.get('marja_neta_pct')),
            }),
        ],
        'extra_tables': [],
        'sheets': {f'Clienți {an}': rows},
        'trend': None,
    }


_BUILDERS = {
    'team': _team,
    'clients': _clients,
}

REPORTS = tuple(_BUILDERS)


def build_context(report, an, luna=None, filters=None):
    """Context for one list/report export, or None when the request is invalid.

    The caller turns None into a 404. `luna` filters to a single month; when it
    is absent the period is year-to-date up to the last month that has data,
    exactly as the pages do. `luna=0` means "no month filter" — the underlying
    queries disagree about what a literal 0 means, so it is normalised here.
    """
    builder = _BUILDERS.get(report)
    if builder is None:
        return None
    if luna == 0:
        luna = None
    if luna and not 1 <= luna <= 12:
        return None
    max_luna = None if luna else queries.max_luna_for_year(an)
    ctx = builder(an, luna, max_luna, filters or {})
    ctx['subtitle'] = period_label(an, luna, max_luna)
    return ctx
