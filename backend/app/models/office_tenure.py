from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

OFFICE_TYPES = ("us_house", "us_senate", "fl_house", "fl_senate")
# Why a tenure ended (Todoist 6hvxq2x37jGMjR5G). `end_date` is when the person
# actually left; `scheduled_end` is when the term runs out, so a sitting
# member has a scheduled_end and no end_date.
END_REASONS = (
    "lost_general", "lost_primary", "term_limited", "did_not_run", "resigned", "removed", "died", "other_office",
)


class OfficeTenure(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One person holding one office for one dated stretch.

    People stay separate from offices: a member who served in the Florida
    legislature and then Congress is one person with two tenures. A tenure is
    linked to a person only on a stable ID or after a human confirms it.
    """

    __tablename__ = "office_tenures"
    __table_args__ = (
        UniqueConstraint("person_entity_id", "office_type", "district", "start_date", name="uq_office_tenures_term"),
        CheckConstraint(f"office_type IN {OFFICE_TYPES}", name="ck_office_tenures_office"),
        CheckConstraint(f"end_reason IS NULL OR end_reason IN {END_REASONS}", name="ck_office_tenures_reason"),
        CheckConstraint("end_reason IS NULL OR end_date IS NOT NULL", name="ck_office_tenures_reason_needs_end"),
    )

    person_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    office_type: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(2), nullable=False, default="FL")
    district: Mapped[int | None] = mapped_column(Integer)  # None for the US Senate
    senate_class: Mapped[int | None] = mapped_column(Integer)
    party: Mapped[str | None] = mapped_column(String(50))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    scheduled_end: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    end_reason: Mapped[str | None] = mapped_column(String(20))
    end_reason_source_url: Mapped[str | None] = mapped_column(Text)
    official_url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(60), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    person: Mapped["Entity"] = relationship()
