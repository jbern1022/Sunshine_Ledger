from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BillLayerCriteria(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Impact Lens criteria for ONE entry of ONE who_it_affects layer version.

    Derived data: the entry's quote and text stay the record; these rows only
    say how a reader's answers are tested against it. Append-only and keyed to
    an immutable layer version, so remapping (a new vocabulary or method
    version) inserts rows and never touches the Who layer.
    See the Notion design "Impact Lens Structured Criteria".

    `criteria` is the output of app.impact_lens.criteria.validate_criteria.
    """

    __tablename__ = "bill_layer_criteria"
    __table_args__ = (
        UniqueConstraint(
            "bill_layer_id", "entry_index", "vocabulary_version", "method_version", name="uq_bill_layer_criteria_version"
        ),
    )

    bill_layer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bill_layers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_index: Mapped[int] = mapped_column(Integer, nullable=False)
    vocabulary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    method_version: Mapped[str] = mapped_column(String(80), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(100), nullable=False)
    criteria: Mapped[dict] = mapped_column(JSONB, nullable=False)

    reviews: Mapped[list["BillLayerCriteriaReview"]] = relationship(
        back_populates="criteria_row", cascade="all, delete-orphan", order_by="BillLayerCriteriaReview.created_at"
    )


class BillLayerCriteriaReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person's decision on one criteria row. Append-only, kept apart so
    reviewing never edits the reviewed row. `reviewer` and `note` are internal."""

    __tablename__ = "bill_layer_criteria_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('approved', 'rejected')", name="ck_bill_layer_criteria_reviews_decision"),
        Index(
            "uq_bill_layer_criteria_reviews_one_approval",
            "criteria_id",
            unique=True,
            postgresql_where=text("decision = 'approved'"),
        ),
    )

    criteria_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bill_layer_criteria.id", ondelete="CASCADE"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    criteria_row: Mapped["BillLayerCriteria"] = relationship(back_populates="reviews")
