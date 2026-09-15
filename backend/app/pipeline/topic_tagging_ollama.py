"""Ollama fallback topic classification for local bills.

Miami/Jacksonville bills (Legistar, iQM2) carry no subject field at all,
unlike LegiScan's state bills -- this classifies them into the same badge
taxonomy using the local Ollama model. `tag_source="ollama"` is recorded
separately from LegiScan tags (see app.pipeline.topic_tagging) so local-bill
tag quality can be audited apart from state-verified ones, per the
2026-09-08 Roadmap decision.
"""

from __future__ import annotations

import json
import logging
import re
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tag import BillTag
from app.pipeline.summarize import OllamaClient, OllamaError
from app.pipeline.topic_tagging import assign_tags_for_bill
from app.pipeline.topic_tagging_seed import TAGS

logger = logging.getLogger(__name__)

VALID_SLUGS = frozenset(slug for slug, _label in TAGS)
GOVERNANCE_FALLBACK = ["governance"]

_CATEGORY_LIST = "\n".join(f"- {slug}: {label}" for slug, label in TAGS)

MAX_DESCRIPTION_CHARS = 4_000  # local bill descriptions are short titles, not full text -- generous headroom

CLASSIFY_PROMPT = """You are categorizing a piece of local government legislation into topic badges for a civic transparency website.

Bill: {title}

Description:
\"\"\"
{description}
\"\"\"

Choose every badge category below that clearly applies. A bill can have more than one. If nothing fits clearly, choose only "governance".

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


def classify_local_bill_topics(
    title: str, description: str, client: OllamaClient | None = None
) -> list[str]:
    """Returns a list of valid tag slugs. Never empty -- falls back to
    ["governance"] if the Ollama call fails, the response can't be parsed as
    a JSON array, or none of its picks are recognized slugs. This matches
    the "never silently dropped" principle already established for the
    LegiScan SubjectMapping path (see topic_tagging.resolve_tag_for_subject).
    """
    client = client or OllamaClient()
    prompt = CLASSIFY_PROMPT.format(
        title=title, description=(description or "")[:MAX_DESCRIPTION_CHARS], category_list=_CATEGORY_LIST
    )

    try:
        response = client.generate(prompt)
    except (httpx.HTTPError, OllamaError):
        logger.warning("Ollama topic classification call failed for bill %r; falling back to governance", title)
        return list(GOVERNANCE_FALLBACK)

    raw = _extract_json_array(response)
    if raw is None:
        logger.warning("Could not parse Ollama topic classification response for bill %r: %r", title, response)
        return list(GOVERNANCE_FALLBACK)

    slugs: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        slug = item.strip().lower()
        if slug in VALID_SLUGS:
            if slug not in slugs:
                slugs.append(slug)
        else:
            logger.warning("Ollama returned an unrecognized tag slug %r for bill %r; dropping it", item, title)

    return slugs or list(GOVERNANCE_FALLBACK)


def tag_local_bill(
    db: Session,
    bill_entity_id: uuid.UUID,
    *,
    title: str,
    description: str,
    client: OllamaClient | None = None,
) -> list[BillTag]:
    """Classify and tag a local (Legistar/iQM2) bill, called from the
    ingestion pipelines.

    Skips entirely if this bill already carries any ollama-sourced tag --
    Legistar/iQM2 ingestion has no change_hash skip like LegiScan, so
    without this a bill would be re-classified (an extra local-model call)
    on every single ingestion run.

    Unlike the LegiScan raw_subjects path, assign_tags_for_bill can't raise
    here if tag seed data is missing: with no raw_subjects passed, it never
    reaches the Governance-lookup code path that raises RuntimeError, and
    instead silently matches zero of the classified slugs against an empty
    Tag table -- effectively becoming a no-op. Logging that distinctly
    would need its own DB check; not worth it for what degrades safely
    either way.
    """
    already_tagged = db.execute(
        select(BillTag.id).where(BillTag.bill_entity_id == bill_entity_id, BillTag.tag_source == "ollama")
    ).first()
    if already_tagged is not None:
        return []

    slugs = classify_local_bill_topics(title, description, client=client)
    return assign_tags_for_bill(db, bill_entity_id, ollama_tag_slugs=slugs)
