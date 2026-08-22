from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single displayable statement about a bill (e.g. one 'what it does'
    summary, one 'who it affects' summary, one status update).

    Sources are attached per-claim (not per-bill) so each claim can show its
    own lightweight trust indicator (source count) per BRD 5.4, with full
    citations hidden by default and expandable inline.
    """

    __tablename__ = "claims"

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # what_it_does | who_it_affects | status_update
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "llm:llama3.1" or "manual_review"

    # sha256 of exactly what produced this claim (source text + model +
    # prompt version). Lets the batch job skip bills whose input hasn't
    # changed -- BRD 6's cost-aware requirement -- and, just as importantly,
    # re-summarize the ones whose input *has* changed, which the old
    # "skip anything with claims" rule could never do. Null on claims
    # written before this column existed, and on manual_review claims.
    input_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    bill_entity: Mapped["Entity"] = relationship(back_populates="claims")
    source_links: Mapped[list["ClaimSource"]] = relationship(back_populates="claim", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Claim {self.claim_type} for {self.bill_entity_id}>"


class ClaimSource(Base):
    """Join table: which Sources back a given Claim (many-to-many)."""

    __tablename__ = "claim_sources"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )

    claim: Mapped["Claim"] = relationship(back_populates="source_links")
    source: Mapped["Source"] = relationship(back_populates="claim_links")
