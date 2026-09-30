from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class LegiScanCallCount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """LegiScan API calls our code made, per month and operation.

    Every run adds its calls here (legiscan.report_api_usage), so
    month-to-date usage is a query rather than a trip to LegiScan's
    dashboard. The dashboard stays the source of truth: it also counts
    anything made outside this code.
    """

    __tablename__ = "legiscan_call_counts"
    __table_args__ = (UniqueConstraint("month", "operation"),)

    month: Mapped[date] = mapped_column(Date, nullable=False)  # first day of the month (UTC)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
