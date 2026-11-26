from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UsageCount(Base):
    """Daily activity totals (docs/USAGE_COUNTS_DESIGN.md).

    One row per (day, event, page kind). Deliberately nothing else: no
    identifier, URL, bill/person id, IP or user agent has a column to land
    in, so the table cannot become a visitor log.
    """

    __tablename__ = "usage_counts"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    event: Mapped[str] = mapped_column(String(20), primary_key=True)
    page_kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
