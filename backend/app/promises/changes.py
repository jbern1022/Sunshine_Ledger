"""Same-URL document replacement, detection only ($100 AWS gate, Todoist
6j5JXcvrHw3Wr3Hp).

A page fetched again at the same URL that comes back with different bytes is
a change. Each change pairs two snapshots that both already exist on disk by
content hash and in the evidence vault (scripts/evidence-sync.sh copies every
snapshot under snapshots/<storage_path>), so both versions are kept without
any new storage. This module only lists the changes; the nightly evidence sync
writes them into that night's signed manifest, which is the record. Nothing
is shown publicly yet (that is the $150 gate).

`text_changed` separates real edits from markup churn (tracking tokens,
nonces, rotating ads): it compares the visible text (snapshot_text) of both
bodies. Only `text_changed: true` needs a person to look.

Run: python -m app.promises.changes [--since-hours 26]   (JSON on stdout)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SiteSnapshot
from app.promises.snapshot_text import snapshot_text


def _vault_path(snap: SiteSnapshot) -> str | None:
    return f"snapshots/{snap.storage_path}" if snap.storage_path else None


def find_changes(
    db: Session, *, since: datetime | None = None, read_body: Callable[[str], bytes | None] | None = None,
) -> list[dict]:
    """Consecutive live fetches of one (site, URL) whose bytes differ, the
    newer fetched at or after `since`. Internet Archive copies are not
    compared: an old capture against a live page is not a replacement."""
    rows = db.execute(
        select(SiteSnapshot)
        .where(SiteSnapshot.status == "ok", SiteSnapshot.content_hash.isnot(None),
               SiteSnapshot.from_archive_timestamp.is_(None))
        .order_by(SiteSnapshot.site_id, SiteSnapshot.url, SiteSnapshot.fetched_at)
    ).scalars().all()
    out: list[dict] = []
    for old, new in zip(rows, rows[1:]):
        if (old.site_id, old.url) != (new.site_id, new.url) or old.content_hash == new.content_hash:
            continue
        if since is not None and new.fetched_at < since:
            continue
        text_changed = None
        if read_body is not None and old.storage_path and new.storage_path:
            a, b = read_body(old.storage_path), read_body(new.storage_path)
            if a is not None and b is not None:
                text_changed = snapshot_text(a) != snapshot_text(b)
        out.append({
            "url": new.url,
            "site_id": str(new.site_id),
            "old": {"sha256": old.content_hash, "fetched_at": old.fetched_at.isoformat(timespec="seconds"),
                    "snapshot_id": str(old.id), "vault_path": _vault_path(old)},
            "new": {"sha256": new.content_hash, "fetched_at": new.fetched_at.isoformat(timespec="seconds"),
                    "snapshot_id": str(new.id), "vault_path": _vault_path(new)},
            "text_changed": text_changed,
            "review": "needs review" if text_changed else ("markup only" if text_changed is False else "body missing"),
        })
    return out


def _reader(root: Path) -> Callable[[str], bytes | None]:
    def read(rel: str) -> bytes | None:
        p = root / rel
        return p.read_bytes() if p.is_file() else None
    return read


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since-hours", type=float, default=26.0, help="only changes fetched in this window (default 26)")
    ap.add_argument("--all", action="store_true", help="every change ever recorded")
    args = ap.parse_args(argv)
    since = None if args.all else datetime.now(timezone.utc) - timedelta(hours=args.since_hours)
    from app.db import SessionLocal

    with SessionLocal() as db:
        changes = find_changes(db, since=since, read_body=_reader(Path(settings.snapshot_dir)))
    json.dump(changes, sys.stdout, indent=2)
    sys.stdout.write("\n")
    flagged = sum(1 for c in changes if c["text_changed"])
    print(f"source changes: {len(changes)} ({flagged} need review)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
