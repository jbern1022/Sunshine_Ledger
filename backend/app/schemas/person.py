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


class PersonVoteItem(BaseModel):
    """One roll-call vote this legislator cast. Plain fact only -- how they
    voted, not a score or a consistency judgement."""

    entity_id: uuid.UUID
    bill_number: str
    bill_name: str
    vote: str
    roll_call_description: str | None
    date: str | None


class PersonDetail(PersonListItem):
    bills: list[PersonBillItem]
    votes: list[PersonVoteItem]


class PersonListResponse(BaseModel):
    total: int
    items: list[PersonListItem]
