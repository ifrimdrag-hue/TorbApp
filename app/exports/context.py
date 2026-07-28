"""Primitives shared by the entity and overview export context builders.

`exports.entities` resolves one identifier; `exports.overviews` resolves a set
of filters. Both emit the same context dict, so `ppt_export.build_entity_ppt`
and `excel_export.send_excel` consume either without a branch.
"""

MONTHS_RO_FULL = [
    'Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
    'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie',
]
MONTHS_RO_SHORT = ['Ian', 'Feb', 'Mar', 'Apr', 'Mai', 'Iun',
                   'Iul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# The workbook sheet is the full-data artifact (unlike the deck table, which
# declares its own top-N truncation), so its underlying queries must pull
# effectively all rows. Several of them bind `LIMIT :limit` and SQLite raises
# on a NULL bind there, so "unlimited" is expressed as a number comfortably
# above any real row count.
SHEET_ROW_LIMIT = 100_000


def period_label(an, luna, max_luna):
    """Human-readable period, so a filtered export is never read as a full year."""
    if luna:
        return f"{an} · {MONTHS_RO_FULL[luna - 1]}"
    if max_luna and max_luna < 12:
        return f"{an} · Ian–{MONTHS_RO_SHORT[max_luna - 1]}"
    return str(an)


def slug(text, maxlen):
    return (text or '').replace(' ', '_').replace('/', '_')[:maxlen]


def slug_with_year(prefix, ident, an, maxlen):
    """Slug that always keeps the trailing `_<year>` — the identifier is
    truncated instead of the whole composed string, so a long ident never
    eats the year suffix (pre-branch behaviour)."""
    suffix = f"_{an}"
    ident = (ident or '').replace(' ', '_').replace('/', '_')
    budget = max(maxlen - len(prefix) - 1 - len(suffix), 0)
    return f"{prefix}_{ident[:budget]}{suffix}"


def table(title, left, width, rows, mapper, limit=15):
    """One deck table. States its own truncation so a top-N never reads as a total."""
    rows = rows or []
    mapped = [mapper(r) for r in rows[:limit]]
    caption = title if len(rows) <= limit else f"{title} — top {limit} din {len(rows)}"
    return {
        'title': caption,
        'left': left,
        'width': width,
        'headers': list(mapped[0].keys()) if mapped else [],
        'rows': mapped,
    }


def trend(rows):
    """{year: [12 monthly val_neta]} for the trend chart."""
    out = {}
    for r in rows:
        luna = r.get('luna')
        if not luna:
            continue
        out.setdefault(r['an'], [0] * 12)[int(luna) - 1] = r.get('val_neta') or 0
    return out


def pct(part, whole):
    return round((part or 0) * 100.0 / whole, 1) if whole else None
