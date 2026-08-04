from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class FlagCreate(BaseModel):
    bill_entity_id: uuid.UUID
    claim_id: uuid.UUID | None = None
    reason_text: str = Field(min_length=5, max_length=2000)
    reporter_email: EmailStr | None = None


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    bill_entity_id: uuid.UUID
    claim_id: uuid.UUID | None
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
    reason_text: str
    reporter_email: str | None
    status: str
    created_at: datetime


class FlagStatusUpdate(BaseModel):
    status: str = Field(pattern="^(pending|reviewed|dismissed)$")
