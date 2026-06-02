"""Persistenta pachete (gifting + trendyol) in data/pachete.json.

Schema:
{
  "gifting":  [ ... bundle gifting ... ],
  "trendyol": [ ... bundle trendyol ... ]
}

Gifting bundle:
{
  id, name, theme, source ("ai_random"|"manual"),
  products: [{ean, cod_articol, name, brand, qty, price_min, price_v, price_max}],
  totals: {cost, standard, max},
  ai_prices: {percent_off: {...}, psychological: {...}, info_only: {...}},
  final_price: float | null,
  margin_pct: float | null,
  status: "draft" | "approved",
  notes, created_at, updated_at
}

Trendyol bundle:
{
  id, ean, cod_articol, name, brand,
  qty: int,
  price_v: float, price_min: float,
  shipping_cost: 11.0,
  ai_suggested_price: float,
  final_price: float,
  margin_total: float, margin_pct: float,
  status: "approved",
  notes, created_at, updated_at
}
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
FILE = DATA_DIR / "pachete.json"

DEFAULT: dict[str, Any] = {"gifting": [], "trendyol": []}


def _load() -> dict[str, Any]:
    if not FILE.exists():
        return json.loads(json.dumps(DEFAULT))
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(json.dumps(DEFAULT))
    for k, v in DEFAULT.items():
        if k not in data:
            data[k] = v
    return data


def _save(state: dict[str, Any]) -> None:
    FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> str:
    return datetime.now().isoformat()


def list_gifting() -> list[dict]:
    return _load().get("gifting", [])


def list_trendyol() -> list[dict]:
    return _load().get("trendyol", [])


def get_state() -> dict:
    return _load()


def upsert_gifting(item: dict) -> dict:
    state = _load()
    items = state.get("gifting", [])
    if not item.get("id"):
        item["id"] = new_id()
        item["created_at"] = now()
    item["updated_at"] = now()

    for i, existing in enumerate(items):
        if existing["id"] == item["id"]:
            item["created_at"] = existing.get("created_at", now())
            items[i] = item
            state["gifting"] = items
            _save(state)
            return item
    items.append(item)
    state["gifting"] = items
    _save(state)
    return item


def upsert_trendyol(item: dict) -> dict:
    state = _load()
    items = state.get("trendyol", [])
    if not item.get("id"):
        item["id"] = new_id()
        item["created_at"] = now()
    item["updated_at"] = now()

    for i, existing in enumerate(items):
        if existing["id"] == item["id"]:
            item["created_at"] = existing.get("created_at", now())
            items[i] = item
            state["trendyol"] = items
            _save(state)
            return item
    items.append(item)
    state["trendyol"] = items
    _save(state)
    return item


def delete_gifting(item_id: str) -> bool:
    state = _load()
    before = len(state["gifting"])
    state["gifting"] = [x for x in state["gifting"] if x["id"] != item_id]
    if len(state["gifting"]) == before:
        return False
    _save(state)
    return True


def delete_trendyol(item_id: str) -> bool:
    state = _load()
    before = len(state["trendyol"])
    state["trendyol"] = [x for x in state["trendyol"] if x["id"] != item_id]
    if len(state["trendyol"]) == before:
        return False
    _save(state)
    return True


def get_gifting(item_id: str) -> dict | None:
    return next((x for x in list_gifting() if x["id"] == item_id), None)


def get_trendyol(item_id: str) -> dict | None:
    return next((x for x in list_trendyol() if x["id"] == item_id), None)
