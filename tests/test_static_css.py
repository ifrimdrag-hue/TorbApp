import re
from pathlib import Path

CSS_PATH = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "style.css"

RULE_RE = re.compile(r"([^{}]+)\{([^}]*)\}")


def _shorthand_right(value):
    parts = value.split()
    if len(parts) == 1:
        return parts[0]
    return parts[1]


COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def _select_right_padding_rem(css_text):
    css_text = COMMENT_RE.sub("", css_text)
    right = None
    for selectors, body in RULE_RE.findall(css_text):
        names = [s.strip() for s in selectors.split(",")]
        if ".table-filter-row select" not in names:
            continue
        for prop, val in re.findall(r"([\w-]+)\s*:\s*([^;]+);", body):
            if prop == "padding-right":
                right = val.strip()
            elif prop == "padding":
                right = _shorthand_right(val.strip())
    assert right is not None, "no padding rule found for .table-filter-row select"
    assert right.endswith("rem"), f"unexpected unit in padding-right: {right}"
    return float(right[:-3])


def test_table_filter_select_padding_clears_dropdown_arrow():
    """BUG: the column-filter <select> (e.g. Brand filter on client.html)
    overrode Bootstrap's padding-right, leaving no room for the
    background-image caret, so it rendered on top of the selected text."""
    css_text = CSS_PATH.read_text(encoding="utf-8")
    right_rem = _select_right_padding_rem(css_text)
    assert right_rem >= 1.0, (
        f"'.table-filter-row select' padding-right is only {right_rem}rem — "
        "too small to clear Bootstrap's dropdown arrow icon"
    )
