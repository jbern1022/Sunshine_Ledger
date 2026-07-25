from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Relationship(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A modeled connection between two entities (BRD glossary: Relationship).

    E.g. a Person entity has relationship_type="sponsor" pointing to a Bill entity.
    """

    __tablename__ = "relationships"

    from_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    to_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # sponsor | co_sponsor | represents | donor | owner
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL")
    )

    from_entity: Mapped["Entity"] = relationship(foreign_keys=[from_entity_id])
    to_entity: Mapped["Entity"] = relationship(foreign_keys=[to_entity_id])

    def __repr__(self) -> str:
        return f"<Relationship {self.relationship_type} {self.from_entity_id}->{self.to_entity_id}>"
