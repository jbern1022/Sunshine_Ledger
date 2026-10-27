"""Ollama topic classification for bills without usable subject data.

Miami/Jacksonville bills (Legistar, iQM2) carry no subject field at all,
and LegiScan's `subjects` turned out to be empty for every FL state bill
on this API tier (checked again 2026-09-25 against the session datasets),
so both are classified into the same badge taxonomy by the local Ollama
model. `tag_source="ollama"` is recorded
separately from LegiScan tags (see app.pipeline.topic_tagging) so local-bill
tag quality can be audited apart from state-verified ones, per the
2026-09-08 Roadmap decision.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tag import BillTag, BillTagRun, Tag, TagQuarantine
from app.pipeline.summarize import OllamaClient, OllamaError
from app.pipeline.topic_tagging import assign_tags_for_bill, set_bill_tag_active
from app.pipeline.topic_tagging_seed import TAGS

logger = logging.getLogger(__name__)

VALID_SLUGS = frozenset(slug for slug, _label in TAGS)
GOVERNANCE_FALLBACK = ["governance"]

_CATEGORY_LIST = "\n".join(f"- {slug}: {label}" for slug, label in TAGS)

LOCAL_KIND = "local government"
STATE_KIND = "Florida state"

MAX_DESCRIPTION_CHARS = 4_000  # local bill descriptions are short titles, not full text -- generous headroom

CLASSIFY_PROMPT = """You are categorizing a piece of {kind} legislation into topic badges for a civic transparency website.

Bill: {title}

Description:
\"\"\"
{description}
\"\"\"

Choose every badge category below that clearly applies. A bill can have more than one. Do NOT include "governance" alongside another category just because the bill is a piece of {kind} legislation -- every bill is that. Choose "governance" only when nothing more specific applies, and choose it alone in that case.

Categories (respond using the slug, not the label):
{category_list}

Respond with ONLY a JSON array of matching slugs, nothing else. Example: ["housing", "taxes_budget"]
"""


def _extract_json_array(text: str) -> list | None:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


@dataclass
class Classification:
    """What the model said, kept apart from what the pipeline does about it.
    `slugs` holds only allowlisted slugs. `outcome` is ok (at least one valid
    slug, or a deliberate Governance answer), empty (answered, nothing valid)
    or failed (call or parse failed: nothing can be concluded)."""

    slugs: list[str]
    unknown: list[str] = field(default_factory=list)
    outcome: str = "ok"
    detail: str | None = None


def classify_local_bill_topics_detailed(
    title: str, description: str, client: OllamaClient | None = None, *, kind: str = LOCAL_KIND
) -> Classification:
    client = client or OllamaClient()
    prompt = CLASSIFY_PROMPT.format(
        kind=kind,
        title=title,
        description=(description or "")[:MAX_DESCRIPTION_CHARS],
        category_list=_CATEGORY_LIST,
    )

    try:
        response = client.generate(prompt)
    except (httpx.HTTPError, OllamaError) as exc:
        logger.warning("Ollama topic classification call failed for bill %r", title)
        return Classification([], outcome="failed", detail=f"call failed: {type(exc).__name__}"[:300])

    raw = _extract_json_array(response)
    if raw is None:
        logger.warning("Could not parse Ollama topic classification response for bill %r: %r", title, response)
        return Classification([], outcome="failed", detail="response was not a JSON array")

    slugs: list[str] = []
    unknown: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        slug = item.strip().lower()
        if slug in VALID_SLUGS:
            if slug not in slugs:
                slugs.append(slug)
        elif slug and slug not in unknown:
            logger.warning("Ollama returned an unrecognized tag slug %r for bill %r; quarantining it", item, title)
            unknown.append(slug[:100])

    # The prompt says to pick "governance" only when nothing more specific
    # applies, but llama3.1:8b adds it alongside a specific topic most of
    # the time (465 of 651 local bills, 13 of 21 sampled state bills on
    # 2026-09-25), which puts a meaningless Governance badge on most bills.
    # Enforce the rule here.
    if len(slugs) > 1 and "governance" in slugs:
        slugs.remove("governance")

    if not slugs:
        return Classification(list(GOVERNANCE_FALLBACK), unknown, outcome="empty",
                              detail="no allowlisted slug in the answer")
    return Classification(slugs, unknown)


def classify_local_bill_topics(
    title: str, description: str, client: OllamaClient | None = None, *, kind: str = LOCAL_KIND
) -> list[str]:
    """Returns a list of valid tag slugs. Never empty -- falls back to
    ["governance"] if the Ollama call fails, the response can't be parsed as
    a JSON array, or none of its picks are recognized slugs. This is the
    display-safe view; tag_local_bill uses classify_local_bill_topics_detailed
    so a failed call is retried instead of being stored as Governance.
    """
    result = classify_local_bill_topics_detailed(title, description, client=client, kind=kind)
    return result.slugs or list(GOVERNANCE_FALLBACK)


def input_hash(title: str, description: str) -> str:
    """Hash of exactly what the classifier sees, so an amended title or
    description is noticed."""
    text = f"{title}\n{(description or '')[:MAX_DESCRIPTION_CHARS]}"
    return hashlib.sha256(text.encode()).hexdigest()


def _quarantine(db: Session, bill_entity_id: uuid.UUID, slugs: list[str], title: str) -> None:
    existing = set(
        db.execute(
            select(TagQuarantine.proposed_slug).where(TagQuarantine.bill_entity_id == bill_entity_id)
        ).scalars()
    )
    for slug in slugs:
        if slug not in existing:
            db.add(TagQuarantine(bill_entity_id=bill_entity_id, proposed_slug=slug, tag_source="ollama",
                                 bill_title=title[:300], status="pending"))


def tag_local_bill(
    db: Session,
    bill_entity_id: uuid.UUID,
    *,
    title: str,
    description: str,
    client: OllamaClient | None = None,
    kind: str = LOCAL_KIND,
) -> list[BillTag]:
    """Classify and tag a bill with the local model, called from the
    ingestion pipelines: every local (Legistar/iQM2) bill, and state bills
    whose LegiScan subjects are empty (kind=STATE_KIND).

    Legistar/iQM2 ingestion has no change_hash skip like LegiScan, so without
    a guard a bill would be re-classified (an extra local-model call) on every
    run. The guard is the last run's input hash: unchanged input with a
    finished run is skipped; changed input (an amended title or description)
    is re-classified and the tags the new answer no longer supports are
    hidden; a failed run is retried. A failed call writes no tag at all, so a
    transient outage can't leave a bill with a Governance badge it never
    earned. Slugs outside the allowlist are quarantined for review, never
    added to the taxonomy.

    Bills tagged before runs were recorded get a `legacy` run holding their
    current input, without a new model call.
    """
    digest = input_hash(title, description)
    run = db.execute(select(BillTagRun).where(BillTagRun.bill_entity_id == bill_entity_id)).scalar_one_or_none()
    ollama_tags = list(
        db.execute(
            select(BillTag).where(BillTag.bill_entity_id == bill_entity_id, BillTag.tag_source == "ollama")
        ).scalars()
    )

    if run is None and ollama_tags:
        db.add(BillTagRun(bill_entity_id=bill_entity_id, input_hash=digest, outcome="legacy",
                          ran_at=datetime.now(timezone.utc)))
        db.commit()
        return []
    if run is not None and run.input_hash == digest and run.outcome != "failed":
        return []

    result = classify_local_bill_topics_detailed(title, description, client=client, kind=kind)
    now = datetime.now(timezone.utc)
    if run is None:
        run = BillTagRun(bill_entity_id=bill_entity_id, input_hash=digest, outcome=result.outcome,
                         detail=result.detail, ran_at=now)
        db.add(run)
    else:
        run.input_hash, run.outcome, run.detail, run.ran_at = digest, result.outcome, result.detail, now

    _quarantine(db, bill_entity_id, result.unknown, title)

    if result.outcome == "failed":
        db.commit()
        return []

    # Amended input: hide model tags the new answer no longer supports.
    keep = set(result.slugs)
    if ollama_tags:
        slug_by_tag = {t.id: t.slug for t in db.execute(select(Tag)).scalars()}
        for bt in ollama_tags:
            if bt.active and slug_by_tag.get(bt.tag_id) not in keep:
                set_bill_tag_active(db, bt.id, active=False)

    return assign_tags_for_bill(db, bill_entity_id, ollama_tag_slugs=result.slugs)
