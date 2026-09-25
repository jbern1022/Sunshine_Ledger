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


class AmendmentOut(BaseModel):
    id: uuid.UUID
    amendment_id: int | None
    date: date
    chamber: str | None
    adopted: bool
    # LegiScan's own `description` field is routinely empty in practice;
    # `title` (e.g. "House Committee Amendment #337249") is what actually
    # carries the label -- verified live, see pipeline/amendments.py.
    description: str | None
    # Full amendment text, when the opt-in backfill has fetched it (see
    # backfill_amendment_texts) -- None until then. Powers the diff view.
    amendment_text: str | None


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
    tags: list["TagOut"]


class LayerItemOut(BaseModel):
    text: str
    section_ref: str | None = None
    quote: str | None = None
    assumptions: list[str] = []
    affected_groups: list[str] = []


class LayerVersionOut(BaseModel):
    id: uuid.UUID
    version: int
    evidence_state: str
    review_status: str
    reviewed_at: datetime | None
    scope_note: str
    items: list[LayerItemOut]
    generated_by: str
    method_version: str
    created_at: datetime
    superseded_at: datetime | None
    sources: list[SourceOut]


class LayerBlockOut(BaseModel):
    """One (layer, origin) block: its current version plus history, newest
    first. `origin` is a fixed backend value; the frontend maps it to
    display text through one lookup, never by position or content."""

    origin: str
    current: LayerVersionOut
    earlier_versions: list[LayerVersionOut]


class BillLayersOut(BaseModel):
    bill_says: list[LayerBlockOut] = []
    interpretation: list[LayerBlockOut] = []
    expected_effect: list[LayerBlockOut] = []


class ActionOut(BaseModel):
    """One step of a bill's official action history (LegiScan `history`):
    filed, referred, reported, passed, signed. `important` is LegiScan's
    own importance flag, for a compact "how it became law" view."""

    date: date
    chamber: str | None
    action: str
    important: bool


class BillDetail(BillListItem):
    last_action: str | None
    # Full bill text, when we have it -- kept off BillListItem since it can
    # run tens of thousands of characters and the list view never needs it.
    full_text: str | None
    sponsors: list[SponsorOut]
    claims: list[ClaimOut]
    news: list[NewsItemOut]
    votes: list[RollCallOut]
    demographic_overlays: list["DemographicOverlayOut"]
    amendments: list[AmendmentOut]
    # Oldest first. Empty for sources without an action history (local bills).
    actions: list[ActionOut] = []
    layers: BillLayersOut
    has_staff_analysis: bool


class BillListResponse(BaseModel):
    total: int
    items: list[BillListItem]


class StatusCount(BaseModel):
    """One status and how many bills carry it, for building a filter UI."""

    status: str
    count: int


class TagOut(BaseModel):
    bill_tag_id: uuid.UUID
    slug: str
    label: str
    tag_source: str
    active: bool


class TagCount(BaseModel):
    """One badge and how many (active-tagged) bills carry it, for a filter UI."""

    slug: str
    label: str
    count: int


class BillTagUpdate(BaseModel):
    active: bool


class DemographicMetricOut(BaseModel):
    label: str
    estimate: float | None
    # Always present (never omitted) for an ACS-sourced metric, per BRD 7.
    # Null for BLS metrics -- BLS doesn't publish one for this series.
    margin_of_error: float | None
    unit: str


class DemographicOverlayOut(BaseModel):
    """ACS/BLS "who it affects" context for one badge on this bill.
    `geography_type`/`geography_id` say exactly what geography the numbers
    describe -- a sponsor's district for a state bill, a county for a local
    one -- so the frontend can (and must) label it honestly rather than
    imply the number describes the bill's full reach."""

    badge_slug: str
    badge_label: str
    source: str  # acs | bls
    geography_type: str  # district | county
    geography_id: str
    as_of: str
    metrics: list[DemographicMetricOut]
