from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class StaffAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A nonpartisan legislative-staff analysis PDF for one bill.

    Florida Senate/House staff publish a committee analysis (and often a
    fiscal-impact note) each time a bill clears a committee, so one bill can
    have several of these over its life -- e.g. one per committee stop, each
    reflecting that committee's version. Kept as its own table rather than a
    single column on `bills` (unlike `full_text`, which is the one filed
    bill) so none of that history is thrown away.

    Discovered via LegiScan's `getBill` `supplements` array, not a scraper:
    every Florida entry there carries `title == "Analysis"` (LegiScan's own
    `type`/`type_id` fields are unreliable for this -- observed as "Veto
    Letter"/8 on every real analysis, sampled across 25 live FL bills
    2026-09-21). Fetched via LegiScan's `getSupplement` op rather than the
    `state_link` URL directly -- that URL 404s into a soft-404 HTML page for
    older/rotated links rather than serving the PDF (confirmed 2026-09-21),
    while `getSupplement` returns the same document base64-encoded and has
    proven stable, matching how bill text and amendments are already
    fetched through LegiScan rather than scraped. `state_link` is kept only
    as a citation URL to the state's own copy.

    Layout is unrelated to a filed bill's: plain prose with footnotes, no
    per-line numbering and no CODING legend, so this does NOT reuse
    bill_text.py's `clean_legislative_text` -- see
    pipeline/staff_analysis.py's own (lighter) cleaner.
    """

    __tablename__ = "staff_analyses"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # LegiScan's supplement_id -- the natural dedupe key. A bill can pick up
    # a new analysis on each committee stop, so ingestion is additive
    # (insert-if-new), never an overwrite.
    legiscan_supplement_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)

    # LegiScan's supplement `description`, e.g. "Natural Resources &
    # Disasters Subcommittee (Post-Meeting)" -- the committee that produced
    # this version, not a free-text label we invented.
    committee: Mapped[str | None] = mapped_column(String(300))
    analysis_date: Mapped[date | None] = mapped_column(Date)

    # The flsenate.gov/myfloridahouse.gov PDF URL (LegiScan's `state_link`),
    # kept alongside LegiScan's own mirror URL for citation -- users and
    # reviewers should be able to reach the state's own copy, not just ours.
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    legiscan_url: Mapped[str | None] = mapped_column(Text)

    # Cleaned text of the analysis PDF -- see module docstring on why this
    # uses its own cleaner rather than bill_text.py's.
    text: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<StaffAnalysis committee={self.committee!r} entity_id={self.entity_id}>"
