from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

LAYERS = ("bill_says", "interpretation", "expected_effect")
ORIGINS = ("bill_text", "legislative_staff", "sunshine_ledger_ai")
ALLOWED_PAIRS = frozenset(
    {
        ("bill_says", "bill_text"),
        ("interpretation", "legislative_staff"),
        ("interpretation", "sunshine_ledger_ai"),
        ("expected_effect", "legislative_staff"),
        ("expected_effect", "sunshine_ledger_ai"),
    }
)
EVIDENCE_STATES = ("supported", "insufficient_evidence")

_PAIR_SQL = " OR ".join(f"(layer = '{layer}' AND origin = '{origin}')" for layer, origin in sorted(ALLOWED_PAIRS))


class BillLayer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One version of one block on a bill page: (layer, origin) -- e.g. the
    Sunshine Ledger AI's Interpretation of a bill, version 3.

    Append-only. A changed input inserts version N+1 and stamps
    `superseded_at` on version N; nothing else on a row is ever updated. That
    is what lets the page show earlier versions, and what the Evidence &
    Source Hierarchy doc means by never silently rewriting an interpretation.
    See docs/superpowers/specs/2026-09-23-bill-layers-design.md.

    "Not yet evaluated" is deliberately not a stored state: it is the
    absence of a row. A missing analysis must never read as a finding.
    """

    __tablename__ = "bill_layers"
    __table_args__ = (
        CheckConstraint(_PAIR_SQL, name="ck_bill_layers_allowed_pair"),
        CheckConstraint("evidence_state IN ('supported', 'insufficient_evidence')", name="ck_bill_layers_evidence_state"),
        UniqueConstraint("bill_entity_id", "layer", "origin", "version", name="uq_bill_layers_version"),
        Index(
            "uq_bill_layers_one_current",
            "bill_entity_id",
            "layer",
            "origin",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
    )

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    layer: Mapped[str] = mapped_column(String(30), nullable=False)
    origin: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_state: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_note: Mapped[str] = mapped_column(Text, nullable=False)
    # [{text, section_ref, quote, assumptions: [], affected_groups: []}]
    items: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    method_version: Mapped[str] = mapped_column(String(80), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    source_links: Mapped[list["BillLayerSource"]] = relationship(back_populates="bill_layer", cascade="all, delete-orphan")
    reviews: Mapped[list["BillLayerReview"]] = relationship(
        back_populates="bill_layer", cascade="all, delete-orphan", order_by="BillLayerReview.created_at"
    )

    def __repr__(self) -> str:
        return f"<BillLayer {self.layer}/{self.origin} v{self.version} for {self.bill_entity_id}>"


class BillLayerSource(Base):
    """Join table: which Sources back a given BillLayer version."""

    __tablename__ = "bill_layer_sources"

    bill_layer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bill_layers.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )

    bill_layer: Mapped["BillLayer"] = relationship(back_populates="source_links")
    source: Mapped["Source"] = relationship()


class BillLayerReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person's review of one BillLayer version. Append-only, kept apart
    from bill_layers so reviewing never edits the reviewed row.

    `reviewer` and `note` are internal: never returned by a public endpoint.
    """

    __tablename__ = "bill_layer_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('approved')", name="ck_bill_layer_reviews_decision"),
        Index(
            "uq_bill_layer_reviews_one_approval",
            "bill_layer_id",
            unique=True,
            postgresql_where=text("decision = 'approved'"),
        ),
    )

    bill_layer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bill_layers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    bill_layer: Mapped["BillLayer"] = relationship(back_populates="reviews")
