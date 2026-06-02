from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


CampaignType = Literal["promo", "gifting", "lansare", "sezonier", "giveaway"]
CampaignStatus = Literal["draft", "planned", "active", "completed", "cancelled"]
Channel = Literal["shopify", "emag", "instagram", "facebook"]
DiscountType = Literal["none", "percent_off", "fixed_off", "fixed_price"]
TaskStatus = Literal["todo", "in_progress", "blocked", "done"]
TaskPriority = Literal["low", "medium", "high", "urgent"]
AssigneeType = Literal["internal", "external"]


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: str = ""
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    assignee: str = ""                                     # nume furnizor sau coleg
    assignee_type: AssigneeType = "external"
    deadline: date | None = None
    completed_at: datetime | None = None
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class CampaignProduct(BaseModel):
    sku: str
    codmare: str | None = None
    ean: str | None = None  # optional, ajuta la match cand sku/codmare difera intre sisteme (ex: Delaviuda)
    name: str = ""
    qty_needed: int | None = None  # estimare manuala — daca e None, validator afiseaza doar stocul


class CampaignDiscount(BaseModel):
    """Reducerea / pretul aplicabil produselor din campanie.

    type:
      - none: fara modificare de pret
      - percent_off: 'value' = procent (ex 10 = -10%)
      - fixed_off:   'value' = suma fixa scazuta din pret (in RON)
      - fixed_price: 'value' = pret nou exact (in RON)
    """
    type: DiscountType = "none"
    value: float | None = None


class Campaign(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    type: CampaignType = "promo"
    mechanic: str = ""              # text liber: "Reducere 20%", "2+1 cadou", "Cadou la 200 RON" etc.
    date_start: date
    date_end: date
    channels: list[Channel] = []
    discount: CampaignDiscount = Field(default_factory=CampaignDiscount)
    products: list[CampaignProduct] = []
    budget_alloc: float | None = None
    budget_spent: float | None = None
    status: CampaignStatus = "draft"
    notes: str = ""
    tasks: list[Task] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
