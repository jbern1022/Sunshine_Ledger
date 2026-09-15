from __future__ import annotations

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DemographicOverlay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Cached ACS/BLS demographic-economic data for one geography + badge
    category (Roadmap Phase 2: ACS/BLS overlay for "who it affects").

    Cached rather than fetched live per request -- ACS is annual, BLS is
    monthly, and this app's "cost-aware at scale" posture (same reasoning as
    spatial_contexts being pre-loaded once) applies here too. A batch loader
    (app/pipeline/demographic_overlay_seed.py) populates this; API requests
    only ever read it.

    `geography_type`/`geography_id` matches the format already used
    elsewhere in this codebase: "district"/"HD-101" or "district"/"SD-024"
    (same normalization as spatial_contexts and Entity.attributes["district"]
    on sponsor Entities), or "county"/"Miami-Dade County" (same strings as
    Bill.geo_scope_names).
    """

    __tablename__ = "demographic_overlays"

    geography_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # district | county
    geography_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    badge_slug: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # matches Tag.slug
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # acs | bls

    # [{"label": str, "estimate": number, "margin_of_error": number | None, "unit": str}, ...]
    # margin_of_error is always present (never omitted) when source="acs", per BRD 7.
    # BLS series don't carry a published margin of error, so it's null there.
    metrics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    as_of: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2022" (ACS 5-yr vintage) or "2024-12" (BLS period)

    __table_args__ = (
        UniqueConstraint(
            "geography_type", "geography_id", "badge_slug", "source",
            name="uq_demographic_overlays_geography_badge_source",
        ),
    )

    def __repr__(self) -> str:
        return f"<DemographicOverlay {self.geography_type}:{self.geography_id} badge={self.badge_slug} source={self.source}>"
