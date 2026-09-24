"""Rhetoric-vs-substance: bill title/blurb vs. full bill text.

Cheapest-win alternate framing of the Roadmap's "rhetoric-vs-substance"
differentiator (Todoist parent 6hCMm779QgHgHHjp), reprioritized 2026-09-15
after research found no accessible data source for the original scope
(sponsors' public statements -- see the parent ticket's Notion page for the
full research trail). This compares a bill's own short official title/
description against what its full text actually does -- both already in
the DB, no new external dependency.

Deliberately biased toward NOT flagging a gap. Bill titles are inherently
terse and often branded ("Protecting Florida Families Act") -- that alone
is not deceptive, and a tool that flags most bills as "misleading" would
be both wrong and would erode trust in the ones it's actually right about.
Only material discrepancies (the text does something narrower, broader, or
different from what the title/description implies) count.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, ClaimSource, Entity, Source
from app.pipeline.summarize import OllamaClient

logger = logging.getLogger(__name__)

CLAIM_TYPE = "rhetoric_gap"

MAX_FULL_TEXT_CHARS = 12_000  # same truncation budget as summarize.py

NO_GAP_SENTINEL = "NO_GAP"

RHETORIC_GAP_PROMPT = """You are checking whether a bill's own short official title/description matches what its full legal text actually does, for a civic transparency website.

Bill: {bill_number} — {title}

Official short description:
\"\"\"
{description}
\"\"\"

Full bill text:
\"\"\"
{full_text}
\"\"\"

In the text, [deleted: …] marks wording the bill removes and [added: …] marks wording it adds.

Your default assumption should be that there is NO meaningful gap. Bill titles are inherently short and often use a branded or appealing name (e.g. "Protecting Florida Families Act") -- that alone is completely normal and not deceptive. Only flag a gap when the full text does something MATERIALLY narrower, broader, or different from what the title/description would lead a reader to expect -- for example: the title implies broad protection but the text carves out major exemptions; the title names one purpose but the text's substantive effect is mostly something else; the description omits a significant, unrelated provision buried in the text.

Do NOT flag: ordinary terseness, a branded/catchy name with no substantive mismatch, technical legal phrasing, or the text simply having more detail than the short description (that is expected, not a gap).

Examples:

Title: "Renames a Bridge"
Text: Renames the Smith Memorial Bridge for a local veteran. No other provisions.
Answer: NO_GAP

Title: "Taxpayer Protection Act"
Text: Cuts a specific tax credit for a narrow group, includes an unrelated provision expanding a state agency's enforcement authority with no taxpayer benefit.
Answer: The title implies broad taxpayer protection, but the text's main substantive effect is narrowing a specific tax credit and expanding agency enforcement power — neither obviously protects taxpayers.

Now evaluate the bill above. If there is no meaningful gap, respond with exactly: NO_GAP
Otherwise, in 1-3 plain sentences, describe the specific gap using only what the text supports. Do not speculate about intent or motive — describe the discrepancy between the words, not why it might exist.

Answer:"""


def generate_rhetoric_gap(
    bill_number: str, title: str, description: str, full_text: str, client: OllamaClient | None = None
) -> str | None:
    """Returns the gap description, or None if no gap was flagged (either
    NO_GAP or an unparseable/empty response -- both treated as "nothing to
    report" rather than guessed at). Pure function, no DB access."""
    client = client or OllamaClient()
    prompt = RHETORIC_GAP_PROMPT.format(
        bill_number=bill_number,
        title=title,
        description=description or "(no official short description available)",
        full_text=full_text[:MAX_FULL_TEXT_CHARS],
    )
    response = client.generate(prompt).strip()
    if not response or response.upper().startswith(NO_GAP_SENTINEL):
        return None
    return response


def rhetoric_gap_and_store(db: Session, entity: Entity, primary_source: Source) -> Claim | None:
    """Generate and store a rhetoric_gap claim for this bill, IF one is
    found. Unlike summarize_and_store's what_it_does/who_it_affects (which
    always store something), no claim is written when no gap is flagged --
    storing a "no gap" claim on ~2,000 bills would clutter the claims table
    with negative results nobody needs to read.

    Requires full_text: without it there's nothing to compare the
    description against, only description-vs-itself.
    """
    if entity.bill is None:
        raise ValueError("Entity is not a bill")
    if not entity.bill.full_text:
        return None

    client = OllamaClient()
    gap = generate_rhetoric_gap(
        entity.bill.bill_number, entity.name, entity.bill.description or "", entity.bill.full_text, client=client
    )
    if gap is None:
        return None

    existing = db.execute(
        select(Claim).where(Claim.bill_entity_id == entity.id, Claim.claim_type == CLAIM_TYPE)
    ).scalars().first()

    if existing is not None:
        existing.claim_text = gap
        existing.generated_by = f"llm:{client.model}"
        claim = existing
    else:
        claim = Claim(
            bill_entity_id=entity.id, claim_type=CLAIM_TYPE, claim_text=gap, generated_by=f"llm:{client.model}"
        )
        db.add(claim)
    db.flush()

    already_linked = db.execute(
        select(ClaimSource).where(ClaimSource.claim_id == claim.id, ClaimSource.source_id == primary_source.id)
    ).scalars().first()
    if already_linked is None:
        db.add(ClaimSource(claim_id=claim.id, source_id=primary_source.id))

    db.commit()
    logger.info("Stored rhetoric_gap claim for bill %s", entity.bill.bill_number)
    return claim
