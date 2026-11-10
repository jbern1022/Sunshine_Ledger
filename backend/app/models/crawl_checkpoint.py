from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CrawlCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Where a slow, paced scrape got to, so the next run resumes instead of
    starting over. One row per scraper (e.g. "iqm2:miamifl"); `state` is the
    scraper's own JSON."""

    __tablename__ = "crawl_checkpoints"

    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
