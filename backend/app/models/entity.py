from __future__ import annotations

import enum

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EntityType(str, enum.Enum):
    """Node types in the civic intelligence graph (BRD glossary: Entity).

    Kept as a plain string column (not a DB enum) so new verticals can add
    entity types without a migration, per the Charter's domain-agnostic
    graph requirement.
    """

    BILL = "bill"
    PERSON = "person"
    ORGANIZATION = "organization"
    GOVERNMENT_BODY = "government_body"


class Entity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A node in the civic intelligence graph: a bill, person, org, or government body."""

    __tablename__ = "entities"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)

    # State-agnostic jurisdiction tagging (BRD 6: config-driven, not hardcoded).
    jurisdiction_level: Mapped[str | None] = mapped_column(String(20))  # state | county | city | federal
    jurisdiction_name: Mapped[str | None] = mapped_column(String(200))  # e.g. "FL", "Miami", "Jacksonville"

    # IDs from source systems, e.g. {"legiscan_id": 1234, "legistar_id": "..."}
    external_ids: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Free-form extra attributes so new verticals don't require schema changes.
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    bill: Mapped["Bill | None"] = relationship(back_populates="entity", uselist=False, cascade="all, delete-orphan")
    claims: Mapped[list["Claim"]] = relationship(back_populates="bill_entity", cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(back_populates="entity", cascade="all, delete-orphan")
    spatial_contexts: Mapped[list["SpatialContext"]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_entities_jurisdiction", "jurisdiction_level", "jurisdiction_name"),
    )

    def __repr__(self) -> str:
        return f"<Entity {self.entity_type}:{self.name!r}>"
