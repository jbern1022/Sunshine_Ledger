from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BillTextVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An earlier text version of a bill (e.g. as filed), kept alongside
    Bill.full_text, which is always the latest. For showing what changed
    between the filed bill and the version that passed. One row per
    LegiScan document."""

    __tablename__ = "bill_text_versions"

    bill_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    legiscan_doc_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    version_type: Mapped[str | None] = mapped_column(String(100))  # LegiScan texts[].type, e.g. "Introduced"
    version_date: Mapped[date | None] = mapped_column(Date)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<BillTextVersion doc={self.legiscan_doc_id} {self.version_type}>"
