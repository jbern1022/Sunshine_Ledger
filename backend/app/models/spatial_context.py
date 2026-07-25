from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SpatialContext(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The PostGIS geographic polygon associated with a bill, entity, or event
    (BRD glossary: SpatialContext).

    MVP scope is county/city level (BRD 5.3) — geometry sourced from U.S.
    Census TIGER/Line shapefiles, not per-address.
    """

    __tablename__ = "spatial_contexts"

    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), index=True
    )

    scope_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # statewide | county | city | district
    scope_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)  # e.g. "Miami-Dade County"
    geom_source: Mapped[str | None] = mapped_column(String(200))  # e.g. "US Census TIGER/Line 2024"

    geom: Mapped[str] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False)

    entity: Mapped["Entity | None"] = relationship(back_populates="spatial_contexts")
    event: Mapped["Event | None"] = relationship(back_populates="spatial_contexts")

    def __repr__(self) -> str:
        return f"<SpatialContext {self.scope_type}:{self.scope_name!r}>"
