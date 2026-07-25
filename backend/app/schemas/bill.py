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


class BillListItem(BaseModel):
    """Row shown in the browse/search list — no full source payload, just a trust count."""

    model_config = ConfigDict(from_attributes=True)

    entity_id: uuid.UUID
    bill_number: str
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


class BillDetail(BillListItem):
    last_action: str | None
    full_text_url: str | None
    sponsors: list[SponsorOut]
    claims: list[ClaimOut]
    news: list[NewsItemOut]


class BillListResponse(BaseModel):
    total: int
    items: list[BillListItem]
