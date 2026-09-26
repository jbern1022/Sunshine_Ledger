from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SourceCheck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """When each data source was last successfully checked.

    One row per source, overwritten by each ingestion step when it finishes
    without error. `sources.retrieved_at` can't answer this: it only gets a
    row when something changed, so a quiet night on LegiScan (1 call, 0
    changed bills) would make the state data look days old. Read by
    GET /sources/status for the site's "last checked" notes.
    """

    __tablename__ = "source_checks"

    source_key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_result: Mapped[str | None] = mapped_column(String(200))

    def __repr__(self) -> str:
        return f"<SourceCheck {self.source_key} at {self.last_checked_at}>"
