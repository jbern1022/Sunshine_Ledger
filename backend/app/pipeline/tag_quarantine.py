"""Review tag slugs the local model proposed that are not in the allowlist.

    python -m app.pipeline.tag_quarantine                    # what is waiting, by slug
    python -m app.pipeline.tag_quarantine --resolve zoning --status rejected --reviewer NAME [--note ...]
    python -m app.pipeline.tag_quarantine --resolve zoning --status mapped --tag housing --reviewer NAME

A slug is quarantined once per bill with the bill's title as provenance. A
recurring slug may mean the vocabulary should grow; `--status added` records
that decision, and the vocabulary itself changes in
topic_tagging_seed.TAGS (the classifier's allowlist is built from it).
Resolving never tags a bill: the next classification pass does.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.tag import Tag, TagQuarantine

STATUSES = ("added", "mapped", "rejected")


def pending_summary(db: Session, *, sample: int = 3) -> list[tuple[str, int, list[str]]]:
    """(slug, bills, sample titles), most-proposed first."""
    rows = db.execute(
        select(TagQuarantine.proposed_slug, func.count())
        .where(TagQuarantine.status == "pending")
        .group_by(TagQuarantine.proposed_slug)
        .order_by(func.count().desc(), TagQuarantine.proposed_slug)
    ).all()
    out = []
    for slug, n in rows:
        titles = db.execute(
            select(TagQuarantine.bill_title)
            .where(TagQuarantine.status == "pending", TagQuarantine.proposed_slug == slug)
            .order_by(TagQuarantine.created_at)
            .limit(sample)
        ).scalars()
        out.append((slug, n, [t for t in titles if t]))
    return out


def resolve(
    db: Session, slug: str, status: str, *, reviewer: str, note: str | None = None, tag_slug: str | None = None
) -> int:
    """Record a disposition on every pending row for `slug`. Returns rows changed."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    if not reviewer.strip():
        raise ValueError("a reviewer name is required")
    mapped_tag_id = None
    if status == "mapped":
        tag = db.execute(select(Tag).where(Tag.slug == tag_slug)).scalar_one_or_none() if tag_slug else None
        if tag is None:
            raise ValueError("--status mapped needs --tag naming an existing tag slug")
        mapped_tag_id = tag.id
    rows = list(
        db.execute(
            select(TagQuarantine).where(TagQuarantine.proposed_slug == slug, TagQuarantine.status == "pending")
        ).scalars()
    )
    now = datetime.now(timezone.utc)
    for row in rows:
        row.status, row.reviewer, row.review_note, row.reviewed_at = status, reviewer.strip(), note, now
        row.mapped_tag_id = mapped_tag_id
    db.commit()
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--resolve", metavar="SLUG")
    parser.add_argument("--status", choices=STATUSES)
    parser.add_argument("--tag", help="existing tag slug, for --status mapped")
    parser.add_argument("--reviewer")
    parser.add_argument("--note")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.resolve:
            if not (args.status and args.reviewer):
                parser.error("--resolve needs --status and --reviewer")
            n = resolve(session, args.resolve, args.status, reviewer=args.reviewer, note=args.note, tag_slug=args.tag)
            print(f"{n} row(s) for {args.resolve!r} marked {args.status}.")
        else:
            summary = pending_summary(session)
            if not summary:
                print("No quarantined slugs waiting for review.")
            for slug, n, titles in summary:
                print(f"{slug}: {n} bill(s), e.g. {'; '.join(titles)}")
    finally:
        session.close()
