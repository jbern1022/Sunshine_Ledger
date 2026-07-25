from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Provenance record attached to a fact at write-time (BRD glossary: Source).

    Every ingested fact and every generated claim must reference a Source so
    citations are never fetched or reconstructed after the fact.
    """

    __tablename__ = "sources"

    url: Mapped[str] = mapped_column(Text, nullable=False)
    document_reference: Mapped[str | None] = mapped_column(String(500))
    publisher: Mapped[str | None] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # legiscan_bill | legistar_agenda | official_document | gdelt_article
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    claim_links: Mapped[list["ClaimSource"]] = relationship(back_populates="source", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Source {self.source_type}:{self.url!r}>"
