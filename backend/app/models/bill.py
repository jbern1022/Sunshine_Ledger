from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin


class Bill(TimestampMixin, Base):
    """Domain-specific extension of an Entity (entity_type='bill').

    Kept as a 1:1 side table rather than folding everything into `entities`
    so the core graph schema stays domain-agnostic (BRD 6) while bill
    tracking gets its own typed columns.
    """

    __tablename__ = "bills"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )

    bill_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # e.g. "HB 123"
    session: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "2026 Regular Session"
    chamber: Mapped[str | None] = mapped_column(String(50))  # House | Senate | Council | Commission

    status: Mapped[str] = mapped_column(String(100), nullable=False, default="Introduced")
    introduced_date: Mapped[date | None] = mapped_column(Date)
    last_action_date: Mapped[date | None] = mapped_column(Date)
    last_action: Mapped[str | None] = mapped_column(Text)

    full_text_url: Mapped[str | None] = mapped_column(Text)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)  # legiscan | legistar

    # Short official description from the source system (e.g. LegiScan's own
    # one-line blurb). Not the full bill text, but real/authoritative and
    # cheap to fetch -- used as the LLM summarization input until full PDF
    # bill-text ingestion exists.
    description: Mapped[str | None] = mapped_column(Text)

    # Cleaned text of the filed bill PDF (see pipeline/bill_text.py), which
    # runs 10-75x longer than `description`. Populated separately from
    # ingestion because it costs one extra LegiScan call per bill. Not yet
    # used as the summarization input -- that swap needs the Roadmap's
    # Step 2 quality gate first.
    full_text: Mapped[str | None] = mapped_column(Text)

    # Geographic scope tagging per BRD 5.3, e.g. scope_type="county", scope_names=["Miami-Dade County"]
    geo_scope_type: Mapped[str | None] = mapped_column(String(20))  # statewide | county | city
    geo_scope_names: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    entity: Mapped["Entity"] = relationship(back_populates="bill")

    def __repr__(self) -> str:
        return f"<Bill {self.bill_number} ({self.session})>"
