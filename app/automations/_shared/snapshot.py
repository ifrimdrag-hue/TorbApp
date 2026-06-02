"""Salveaza ultimul raport de stocuri parsat ca JSON, ca sa-l putem folosi
pentru alte automatizari (validator stoc campanii, AI content etc) fara
ca user-ul sa-l reincarce."""

import json
from datetime import datetime
from pathlib import Path

from .report_parser import ParseResult


DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
SNAPSHOT_FILE = DATA_DIR / "latest_stock_snapshot.json"


def save_snapshot(parsed: ParseResult, source_filename: str = "") -> None:
    data = {
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "source_filename": source_filename,
        "rows": [
            {"sku": r.sku, "codmare": r.codmare, "ean": r.ean, "qty": r.qty}
            for r in parsed.rows
        ],
    }
    SNAPSHOT_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_snapshot() -> dict | None:
    if not SNAPSHOT_FILE.exists():
        return None
    return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
