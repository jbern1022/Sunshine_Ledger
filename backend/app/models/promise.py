"""Promise baseline (Todoist 6hvxpp58fXp6cgfp): winners, their own sites,
archived snapshots, and verbatim statements found in them.

Minimal-first, per the ticket: a promise record (source, snapshot, status,
review state) linked to the winner. The full claim model comes later (see
docs/EVIDENCE_MODEL_GAP_MAP.md). Nothing here carries a fulfillment status:
those need human review and are never produced automatically.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

CHAMBERS = ("house", "senate")
RESULT_STATUSES = ("unofficial", "certified")
SITE_KINDS = ("campaign", "official_legislature", "press")
DISCOVERED_VIA = ("state_listing", "official_member_page", "directory", "manual")
SITE_STATUSES = ("unchecked", "live", "offline", "blocked")
SNAPSHOT_STATUSES = ("ok", "blocked_by_robots", "unavailable", "refused")
REVIEW_STATES = ("unreviewed", "flagged", "approved", "rejected", "not_a_commitment")
REVIEW_ACTIONS = ("approve", "reject", "not_a_commitment", "reclassify", "unflag")


class ElectionWinner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Someone who won a Florida legislative seat in a general election.

    Built from the state's results; unofficial first, reconciled to certified.
    `person_entity_id` is set only on a corroborated match (chamber and
    district, plus the name), never on name alone.
    """

    __tablename__ = "election_winners"
    __table_args__ = (
        UniqueConstraint("cycle", "chamber", "district", name="uq_election_winners_seat"),
        CheckConstraint(f"chamber IN {CHAMBERS}", name="ck_election_winners_chamber"),
        CheckConstraint(f"result_status IN {RESULT_STATUSES}", name="ck_election_winners_status"),
    )

    cycle: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    chamber: Mapped[str] = mapped_column(String(10), nullable=False)
    district: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    party: Mapped[str | None] = mapped_column(String(50))
    incumbent: Mapped[bool | None] = mapped_column(Boolean)  # None = not stated by the source
    result_status: Mapped[str] = mapped_column(String(12), nullable=False, default="unofficial")
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    certified_at: Mapped[date | None] = mapped_column(Date)
    person_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), index=True
    )
    # What changed at certification (a different winner, a corrected name), so
    # the move from unofficial to certified is never silent.
    change_log: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    sites: Mapped[list["OfficialSite"]] = relationship(back_populates="winner", cascade="all, delete-orphan")


class OfficialSite(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A page set a winner publishes themselves (campaign site, legislature
    page, press page). Third-party directories may help find one, but are
    never the source of a promise."""

    __tablename__ = "official_sites"
    __table_args__ = (
        UniqueConstraint("winner_id", "url", name="uq_official_sites_winner_url"),
        CheckConstraint(f"site_kind IN {SITE_KINDS}", name="ck_official_sites_kind"),
        CheckConstraint(f"discovered_via IN {DISCOVERED_VIA}", name="ck_official_sites_via"),
        CheckConstraint(f"status IN {SITE_STATUSES}", name="ck_official_sites_status"),
    )

    winner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("election_winners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    site_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    discovered_via: Mapped[str] = mapped_column(String(24), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="unchecked")
    # Internet Archive copy to fall back on when the site is gone.
    archive_url: Mapped[str | None] = mapped_column(Text)
    archive_timestamp: Mapped[str | None] = mapped_column(String(14))

    winner: Mapped["ElectionWinner"] = relationship(back_populates="sites")
    snapshots: Mapped[list["SiteSnapshot"]] = relationship(back_populates="site", cascade="all, delete-orphan")


class SiteSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One fetch of one page. The body is stored by content hash on disk; the
    row records when, what came back, and where it is. A page we could not
    fetch is recorded too, so every site ends 'snapshotted or recorded as
    unavailable'."""

    __tablename__ = "site_snapshots"
    __table_args__ = (
        UniqueConstraint("site_id", "url", "content_hash", name="uq_site_snapshots_content"),
        CheckConstraint(f"status IN {SNAPSHOT_STATUSES}", name="ck_site_snapshots_status"),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("official_sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    page_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer)
    final_url: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(String(200))
    content_hash: Mapped[str | None] = mapped_column(String(64))  # sha256 hex of the body bytes
    byte_length: Mapped[int | None] = mapped_column(Integer)
    storage_path: Mapped[str | None] = mapped_column(Text)
    # Set when the body is an Internet Archive copy: the capture time, kept
    # apart from fetched_at (when we downloaded it).
    from_archive_timestamp: Mapped[str | None] = mapped_column(String(14))
    note: Mapped[str | None] = mapped_column(Text)
    # Set once the extractor has read this snapshot (even if it found nothing),
    # with the snapshot_text version its offsets refer to.
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extracted_text_version: Mapped[int | None] = mapped_column(Integer)

    site: Mapped["OfficialSite"] = relationship(back_populates="snapshots")
    items: Mapped[list["PromiseItem"]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")


class PromiseItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A verbatim passage a model proposed as a commitment, kept only because
    it was found, byte for byte, in the snapshot's text.

    `auto_labels` are drafts from the model (commitment vs. value statement,
    topics) and are labelled automated wherever shown. `review_state` starts
    'unreviewed'. There is deliberately no fulfillment column.
    """

    __tablename__ = "promise_items"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "char_start", "char_end", name="uq_promise_items_span"),
        CheckConstraint(f"review_state IN {REVIEW_STATES}", name="ck_promise_items_state"),
    )

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("site_snapshots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    winner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("election_winners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Offsets into snapshot_text(body); see promises/snapshot_text.py.
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The date the statement was originally made, when the page says so.
    statement_date: Mapped[date | None] = mapped_column(Date)
    auto_labels: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    review_state: Mapped[str] = mapped_column(String(20), nullable=False, default="unreviewed", index=True)
    # Reviewer's own classification once one has looked (overrides the draft).
    reviewed_classification: Mapped[str | None] = mapped_column(String(40))
    flag_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    snapshot: Mapped["SiteSnapshot"] = relationship(back_populates="items")
    winner: Mapped["ElectionWinner"] = relationship()
    flags: Mapped[list["PromiseFlag"]] = relationship(back_populates="item", cascade="all, delete-orphan")
    reviews: Mapped[list["PromiseReview"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="PromiseReview.created_at"
    )


class PromiseFlag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A public 'flag this' on a promise item. Flagged items are reviewed first."""

    __tablename__ = "promise_flags"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("promise_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    reporter_email: Mapped[str | None] = mapped_column(String(320))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    item: Mapped["PromiseItem"] = relationship(back_populates="flags")


class PromiseReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only log of reviewer actions: who, what, when, why."""

    __tablename__ = "promise_reviews"
    __table_args__ = (CheckConstraint(f"action IN {REVIEW_ACTIONS}", name="ck_promise_reviews_action"),)

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("promise_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(100), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(40))
    from_state: Mapped[str] = mapped_column(String(20), nullable=False)
    to_state: Mapped[str] = mapped_column(String(20), nullable=False)

    item: Mapped["PromiseItem"] = relationship(back_populates="reviews")
