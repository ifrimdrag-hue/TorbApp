"""Persistenta campaniilor in fisier JSON local (data/campaigns.json).

Single-user local app — nu avem nevoie de DB sau locking complicat.
"""

import json
from datetime import datetime
from pathlib import Path

from .models import Campaign


DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CAMPAIGNS_FILE = DATA_DIR / "campaigns.json"


def load_all() -> list[Campaign]:
    if not CAMPAIGNS_FILE.exists():
        return []
    raw = json.loads(CAMPAIGNS_FILE.read_text(encoding="utf-8"))
    return [Campaign.model_validate(c) for c in raw]


def save_all(campaigns: list[Campaign]) -> None:
    raw = [c.model_dump(mode="json") for c in campaigns]
    CAMPAIGNS_FILE.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def get(campaign_id: str) -> Campaign | None:
    return next((c for c in load_all() if c.id == campaign_id), None)


def upsert(campaign: Campaign) -> Campaign:
    all_c = load_all()
    for i, existing in enumerate(all_c):
        if existing.id == campaign.id:
            campaign.created_at = existing.created_at
            campaign.updated_at = datetime.now()
            all_c[i] = campaign
            save_all(all_c)
            return campaign
    # new
    campaign.created_at = campaign.created_at or datetime.now()
    campaign.updated_at = datetime.now()
    all_c.append(campaign)
    save_all(all_c)
    return campaign


def delete(campaign_id: str) -> bool:
    all_c = load_all()
    new = [c for c in all_c if c.id != campaign_id]
    if len(new) == len(all_c):
        return False
    save_all(new)
    return True
