from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class FederalEarmark(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One Community Project Funding (House) request or award for a Florida project.

    `stage` says how far it got: "requested" is a member's request, NOT money awarded; "included" means
    the committee's bill contains it; "enacted" means the enacted law funds it. A request is never shown
    as funding. `person_entity_id` is set only when the district and the member's last name both match
    exactly one tenure; otherwise the row keeps the names it came with."""

    __tablename__ = "federal_earmarks"
    __table_args__ = (
        UniqueConstraint("fiscal_year", "stage", "member_last", "district", "subcommittee", "recipient", "description",
                         name="uq_federal_earmarks_row"),
    )

    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(10), nullable=False)  # requested | included | enacted
    chamber: Mapped[str] = mapped_column(String(6), nullable=False)  # house (senate lists are not imported yet)
    member_last: Mapped[str] = mapped_column(String(80), nullable=False)
    member_first: Mapped[str | None] = mapped_column(String(80))
    district: Mapped[str] = mapped_column(String(8), nullable=False, index=True)  # "CD-012"
    party: Mapped[str | None] = mapped_column(String(10))
    subcommittee: Mapped[str] = mapped_column(String(80), nullable=False)
    recipient: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_address: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[int | None] = mapped_column(Integer)  # dollars
    member_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    person_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), index=True
    )
