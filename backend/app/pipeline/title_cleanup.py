"""One-time backfill: tidy the stored titles of local (Legistar) items.

Ingest has run `legistar._tidy_title` on new titles since 2026-10-27, which
drops Jacksonville's "10/27/26 CO Introduced: R" history line and flattens
line breaks. Titles stored before that still carry both (135 of 400
Jacksonville items on the live API, 2026-10-29), and ingest does not revisit
them. Dry run by default; the original text stays in bill.description.

Usage:
    python -m app.pipeline.title_cleanup [--apply]
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Entity
from app.pipeline.legistar import _tidy_title

logger = logging.getLogger(__name__)


def clean_stored_titles(db: Session, *, apply: bool) -> int:
    """Return how many Legistar items have a title that tidying would change."""
    changed = 0
    rows = db.execute(
        select(Entity).where(
            Entity.entity_type == "bill",
            Entity.external_ids["legistar_matter_id"].as_string().is_not(None),
        )
    ).scalars()
    for entity in rows:
        tidy = _tidy_title(entity.name)
        if tidy and tidy != entity.name:
            changed += 1
            if apply:
                entity.name = tidy
    if apply:
        db.commit()
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the changes (default: count only)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        changed = clean_stored_titles(db, apply=args.apply)
    logger.info("%s %d title(s)", "Cleaned" if args.apply else "Would clean", changed)


if __name__ == "__main__":
    main()
