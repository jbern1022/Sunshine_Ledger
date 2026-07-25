from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Flag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user-submitted report of a suspected inaccuracy (BRD 5.5).

    Routes to manual review only — there is no open/crowdsourced editing at
    MVP, so this table has no public read endpoint. `claim_id` is optional:
    a flag can target one specific claim (e.g. a bad summary) or the bill
    as a whole.
    """

    __tablename__ = "flags"

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE")
    )
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    reporter_email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)  # pending | reviewed | dismissed

    bill_entity: Mapped["Entity"] = relationship()
    claim: Mapped["Claim | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Flag {self.status} on {self.bill_entity_id}>"
