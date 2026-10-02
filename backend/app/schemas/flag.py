from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

Category = Literal["factually_wrong", "misleading", "wrong_source", "outdated", "wrong_entity", "other"]
ObjectType = Literal["bill", "claim", "bill_layer", "amendment", "vote", "page_copy"]
Severity = Literal["minor", "material", "critical"]
ChangeType = Literal["update", "correction", "clarification", "retraction", "source_correction"]


class FlagCreate(BaseModel):
    bill_entity_id: uuid.UUID
    claim_id: uuid.UUID | None = None
    # What exactly is challenged. Omitted: the bill as a whole (or claim_id's claim).
    object_type: ObjectType | None = None
    object_id: uuid.UUID | None = None
    object_version: int | None = Field(default=None, ge=1)
    category: Category = "other"
    reason_text: str = Field(min_length=5, max_length=2000)
    evidence_text: str | None = Field(default=None, max_length=4000)
    evidence_url: HttpUrl | None = None
    is_named_party: bool = False
    reporter_email: EmailStr | None = None


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_entity_id: uuid.UUID
    claim_id: uuid.UUID | None
    object_type: str
    category: str
    status: str


class FlagAdminOut(BaseModel):
    """Fuller view for the authenticated review endpoint -- includes the
    reporter's reason text/email and enough bill context to act on it
    without a second lookup."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_entity_id: uuid.UUID
    bill_number: str
    bill_name: str
    claim_id: uuid.UUID | None
    claim_text: str | None
    object_type: str
    object_id: uuid.UUID | None
    object_version: int | None
    category: str
    reason_text: str
    evidence_text: str | None
    evidence_url: str | None
    is_named_party: bool
    reporter_email: str | None
    status: str
    severity: str | None
    disputed_since: datetime | None
    duplicate_of_id: uuid.UUID | None
    decision: str | None
    decision_explanation: str | None
    created_at: datetime
    triaged_at: datetime | None
    decided_at: datetime | None


class FlagTriage(BaseModel):
    """Triage: either dismiss (spam, off-topic, or a duplicate), or set the
    severity and whether the page should say "Disputed - under review"."""

    dismiss: bool = False
    duplicate_of_id: uuid.UUID | None = None
    severity: Severity | None = None
    disputed: bool = False
    note: str | None = Field(default=None, max_length=2000)


class EvidenceLink(BaseModel):
    url: HttpUrl
    role: Literal["supporting", "challenging", "contradicting"]
    note: str | None = Field(default=None, max_length=500)


class CorrectionFields(BaseModel):
    """What changed. The earlier and corrected text are stored, not only
    referenced, so the record stays readable after later versions."""

    change_type: ChangeType
    severity: Severity
    explanation: str = Field(min_length=10, max_length=4000)
    prior_text: str | None = None
    current_text: str | None = None
    prior_version: int | None = None
    current_version: int | None = None
    evidence_links: list[EvidenceLink] = []
    origin: str | None = Field(default=None, max_length=30)
    was_reviewed: bool | None = None
    methodology_version: str | None = Field(default=None, max_length=80)


class FlagDecision(BaseModel):
    """`no_change` needs only an explanation; anything else also records a
    correction (decision 4: every change stays visible with its evidence)."""

    decision: Literal["update", "correction", "clarification", "retraction", "source_correction", "no_change"]
    explanation: str = Field(min_length=10, max_length=4000)
    correction: CorrectionFields | None = None


class CorrectionCreate(CorrectionFields):
    """A correction not started by a public challenge."""

    bill_entity_id: uuid.UUID
    object_type: ObjectType
    object_id: uuid.UUID | None = None
    trigger: Literal["internal_review", "source_change", "methodology_change"]


class CorrectionOut(BaseModel):
    """Public view of a correction record (decided_by is internal)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_entity_id: uuid.UUID
    object_type: str
    object_id: uuid.UUID | None
    prior_version: int | None
    current_version: int | None
    prior_text: str | None
    current_text: str | None
    change_type: str
    severity: str
    trigger: str
    explanation: str
    evidence_links: list[dict]
    origin: str | None
    was_reviewed: bool | None
    methodology_version: str | None
    decided_at: datetime
    decided_by_label: str = "Sunshine Ledger editor"


class DisputeOut(BaseModel):
    """A statement currently under challenge: the page labels it, never hides it."""

    flag_id: uuid.UUID
    object_type: str
    object_id: uuid.UUID | None
    category: str
    severity: str | None
    disputed_since: datetime


class ResponseCreate(BaseModel):
    bill_entity_id: uuid.UUID
    object_type: ObjectType = "bill"
    object_id: uuid.UUID | None = None
    responder_name: str = Field(min_length=2, max_length=200)
    responder_role: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=1500)
    full_text_url: HttpUrl | None = None
    # How identity was checked, shown publicly (decision 3), e.g. "verified
    # via the contact on the candidate's Division of Elections filing".
    verified_via: str = Field(min_length=10, max_length=300)
    received_at: datetime
    supersedes_id: uuid.UUID | None = None


class ResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_entity_id: uuid.UUID
    object_type: str
    object_id: uuid.UUID | None
    responder_name: str
    responder_role: str | None
    text: str
    full_text_url: str | None
    verified_via: str
    received_at: datetime
    superseded_by_id: uuid.UUID | None
