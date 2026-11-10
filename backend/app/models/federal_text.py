from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class FederalBillText(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One published text version of a federal bill (Introduced in House,
    Engrossed, Enrolled ...), kept as the Government Publishing Office
    printed it. Every version is kept; `Bill.full_text` mirrors the latest."""

    __tablename__ = "federal_bill_texts"
    __table_args__ = (UniqueConstraint("bill_entity_id", "source_url", name="uq_federal_bill_texts_source"),)

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_type: Mapped[str | None] = mapped_column(String(100))  # "Introduced in House"
    version_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    findings: Mapped[list["FederalPlaceFinding"]] = relationship(back_populates="text_version", cascade="all, delete-orphan")


class FederalPlaceFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A place in Florida that a federal bill's text names, found by rule (see
    federal/places.py), with the sentence it appears in copied exactly.
    Automatically found; not reviewed by a person."""

    __tablename__ = "federal_place_findings"
    __table_args__ = (
        UniqueConstraint("text_id", "char_start", "char_end", "matched_term", name="uq_federal_place_findings_span"),
    )

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("federal_bill_texts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # state | county | municipality | named_place | disaster
    matched_term: Mapped[str] = mapped_column(String(200), nullable=False)
    counties: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    section: Mapped[str | None] = mapped_column(String(200))
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    method_version: Mapped[str] = mapped_column(String(40), nullable=False)

    text_version: Mapped["FederalBillText"] = relationship(back_populates="findings")
