from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class LensItemOut(BaseModel):
    text: str
    quote: str


class LensEntryOut(BaseModel):
    group: str
    text: str
    quote: str
    conditions: list[LensItemOut] = []
    exceptions: list[LensItemOut] = []
    # impact_lens.criteria.validate_criteria output, or None when this entry
    # has no mapping at the current vocabulary version.
    criteria: dict | None = None
    # A person has approved this mapping. False shows the
    # "Automatically mapped, not yet reviewed" label.
    reviewed: bool = False


class LensOptionOut(BaseModel):
    value: str
    label: str


class LensQuestionOut(BaseModel):
    """One question the bill can ask. `key` is the matcher's answer key
    (role, county, municipality, property_type)."""

    key: str
    label: str
    question: str
    options: list[LensOptionOut]
    # municipality only: the counties each option lies in (a few span two).
    counties: dict[str, list[str]] | None = None


class LensLayerOut(BaseModel):
    id: uuid.UUID
    version: int
    evidence_state: str
    scope_note: str
    method_version: str
    created_at: datetime


class ImpactLensOut(BaseModel):
    """What the browser needs to run the Impact Lens matcher for one bill.
    Takes no user input: a reader's answers never reach the server."""

    bill_entity_id: uuid.UUID
    available: bool
    unavailable_reason: str | None = None
    vocabulary_version: int
    # The matcher may say "Does Not Appear to Apply" only when this is true.
    complete: bool = False
    incomplete_reasons: list[str] = []
    layer: LensLayerOut | None = None
    entries: list[LensEntryOut] = []
    questions: list[LensQuestionOut] = []
