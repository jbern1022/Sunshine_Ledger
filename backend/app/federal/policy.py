"""Which federal bills get the expensive treatment.

Owner decision (Todoist 6hvxx9hHg2G2cWjp): plain-language summaries and topic
tags only for bills a Florida delegation member sponsored or cosponsored.
Every other federal bill carries a title, a status and a link to
Congress.gov, and nothing is generated for it. The nightly summarizers, layer
generator, headline search and rhetoric check all apply this predicate.
"""

from __future__ import annotations

from sqlalchemy import or_

from app.models import Bill, Entity

SOURCE_SYSTEM = "congress"


def eligible_for_generation():
    """SQL clause: not a federal bill, or a federal bill the delegation
    sponsored or cosponsored. Needs Bill and Entity in the query."""
    return or_(Bill.source_system != SOURCE_SYSTEM, Entity.attributes["delegation_sponsored"].as_boolean().is_(True))


def is_eligible(entity: Entity) -> bool:
    bill = entity.bill
    if bill is None or bill.source_system != SOURCE_SYSTEM:
        return True
    return bool((entity.attributes or {}).get("delegation_sponsored"))
