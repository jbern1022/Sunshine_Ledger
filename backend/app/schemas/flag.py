from __future__ import annotations

import uuid

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
