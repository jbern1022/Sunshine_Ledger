from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    publisher: str | None
    source_type: str
    retrieved_at: datetime


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_type: str
    claim_text: str
    generated_by: str
    source_count: int
    sources: list[SourceOut]


class SponsorOut(BaseModel):
    entity_id: uuid.UUID
    name: str
    relationship_type: str


class NewsItemOut(BaseModel):
    id: uuid.UUID
    title: str
    url: str
    publisher: str | None
    published_date: date | None


class IndividualVoteOut(BaseModel):
    person_entity_id: uuid.UUID
    person_name: str
    vote: str


class RollCallOut(BaseModel):
    """A single roll-call vote. Plain facts only -- tallies and who voted
    which way, sourced straight from LegiScan, no scoring or characterization."""

    id: uuid.UUID
    roll_call_id: str
    chamber: str | None
    description: str
    date: date
    yea: int | None
    nay: int | None
    nv: int | None
    absent: int | None
    total: int | None
    passed: bool
    source_url: str | None
    votes: list[IndividualVoteOut]


class BillListItem(BaseModel):
    """Row shown in the browse/search list — no full source payload, just a trust count."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: uuid.UUID
    bill_number: str
    # The bill's actual title. Held on the entity, but never exposed until
    # now -- the UI could only ever show a bill number.
    name: str
    session: str
    chamber: str | None
    status: str
    jurisdiction_level: str | None
    jurisdiction_name: str | None
    geo_scope_type: str | None
    geo_scope_names: list[str]
    introduced_date: date | None
    last_action_date: date | None
    what_it_does: str | None
    source_count: int
    full_text_url: str | None
    primary_sponsor: str | None


class BillDetail(BillListItem):
    last_action: str | None
    sponsors: list[SponsorOut]
    claims: list[ClaimOut]
    news: list[NewsItemOut]
    votes: list[RollCallOut]


class BillListResponse(BaseModel):
    total: int
    items: list[BillListItem]


class StatusCount(BaseModel):
    """One status and how many bills carry it, for building a filter UI."""

    status: str
    count: int
