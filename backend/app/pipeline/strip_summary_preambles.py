"""One-off: remove the model's "Here is a ... summary of the bill:" opener from
stored summaries (app.pipeline.summarize.strip_preamble). New summaries are
cleaned when written; this fixes the ones written before.

    python -m app.pipeline.strip_summary_preambles            # dry run: counts and 3 examples
    python -m app.pipeline.strip_summary_preambles --apply    # update in place

The claim is updated in place (flags on it are kept) and its input hash is not
touched, so nothing is re-summarized. Safe to run twice.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Claim
from app.pipeline.summarize import strip_preamble


def run(db, *, apply: bool) -> list[tuple[str, str]]:
    changed = []
    rows = db.execute(
        select(Claim).where(Claim.claim_type.in_(("what_it_does", "who_it_affects")),
                            Claim.claim_text.op("~*")(r"^\s*(here is|here's|sure|below is)"))
    ).scalars().all()
    for c in rows:
        new = strip_preamble(c.claim_text)
        if new != c.claim_text:
            changed.append((c.claim_text, new))
            if apply:
                c.claim_text = new
    if apply:
        db.commit()
    return changed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    with SessionLocal() as db:
        changed = run(db, apply=args.apply)
    for before, after in changed[:3]:
        print(f"- {before[:120]!r}\n+ {after[:120]!r}")
    print(f"{'updated' if args.apply else 'would update'} {len(changed)} summaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
