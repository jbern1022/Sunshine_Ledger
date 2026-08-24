from __future__ import annotations

import uuid

from pydantic import BaseModel


class PersonListItem(BaseModel):
    """A legislator as shown in a list."""

    entity_id: uuid.UUID
    name: str
    district: str | None
    role: str | None
    party: str | None
    jurisdiction_name: str | None
    sponsored_count: int


class PersonBillItem(BaseModel):
    """One bill a legislator is attached to, and how."""

    entity_id: uuid.UUID
    bill_number: str
    name: str
    status: str
    relationship_type: str  # sponsor | co_sponsor
    last_action_date: str | None
    what_it_does: str | None


class PersonDetail(PersonListItem):
    bills: list[PersonBillItem]


class PersonListResponse(BaseModel):
    total: int
    items: list[PersonListItem]
