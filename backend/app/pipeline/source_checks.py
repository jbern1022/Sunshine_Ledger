"""Record that a data source was checked successfully.

Called at the end of each ingestion step, only after it finishes without
error, so `last_checked_at` means "we looked and got an answer", whether
or not anything had changed. Keys match app.api.sources.SOURCES.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import SourceCheck


def record_check(db: Session, source_key: str, result: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    db.execute(
        pg_insert(SourceCheck)
        .values(source_key=source_key, last_checked_at=now, last_result=(result or "")[:200] or None)
        .on_conflict_do_update(
            index_elements=["source_key"],
            set_={"last_checked_at": now, "last_result": (result or "")[:200] or None},
        )
    )
    db.commit()
