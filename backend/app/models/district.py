from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class MapPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A set of district boundaries in force for a stretch of time. A new plan
    after redistricting means new District rows; old ones stay, so history is
    never rewritten (Todoist 6hvxmFvCHr9x6cGp)."""

    __tablename__ = "map_plans"

    key: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)  # e.g. "fl-state-2022"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False, default="FL")
    # Which set of districts the plan draws; several plans are in force at once.
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="state_legislature", server_default="state_legislature")
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)  # None = still in force
    source_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    districts: Mapped[list["District"]] = relationship(back_populates="map_plan", cascade="all, delete-orphan")


class District(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "districts"
    __table_args__ = (
        UniqueConstraint("map_plan_id", "code", name="uq_districts_plan_code"),
        CheckConstraint("chamber IN ('house', 'senate', 'us_house')", name="ck_districts_chamber"),
    )

    map_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("map_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chamber: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # "HD-101", "SD-024"
    # The boundary polygon lives in spatial_contexts (scope_type "district").
    spatial_context_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spatial_contexts.id", ondelete="SET NULL")
    )

    map_plan: Mapped["MapPlan"] = relationship(back_populates="districts")


_PREFIX = {"house": "HD", "senate": "SD", "us_house": "CD"}


def district_code(chamber: str, number: int) -> str:
    return f"{_PREFIX[chamber]}-{number:03d}"
