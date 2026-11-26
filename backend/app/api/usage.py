"""Privacy-safe usage counts (docs/USAGE_COUNTS_DESIGN.md).

Daily totals of three events by page kind. Nothing identifying is accepted
or stored; the request's user agent and Origin are read only to drop
crawlers and cross-site posts, then discarded.
"""


import datetime as dt
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.config import settings
from app.db import get_db
from app.models import UsageCount
from app.rate_limit import limiter

router = APIRouter(prefix="/usage", tags=["usage"])

Event = Literal["page_view", "bill_read", "source_click"]
PageKind = Literal[
    "home", "browse", "bill", "person", "district", "map", "promises", "corrections", "methodology", "other"
]

# Crawlers, headless browsers and HTTP libraries. Matching drops the event;
# the user agent itself is never stored.
_NOT_A_READER = re.compile(
    r"bot|crawl|spider|slurp|headless|lighthouse|preview|python|curl|wget|httpx|okhttp|java/|go-http|node-fetch|axios",
    re.IGNORECASE,
)


class UsageEvent(BaseModel):
    # Extra fields are refused, not ignored: a client that tries to send an id
    # is a bug to surface, not data to drop quietly.
    model_config = ConfigDict(extra="forbid")

    event: Event
    page_kind: PageKind


def _is_reader(request: Request) -> bool:
    ua = request.headers.get("user-agent") or ""
    if not ua or _NOT_A_READER.search(ua):
        return False
    return request.headers.get("origin") in settings.cors_allowed_origins_list


@router.post("", status_code=204)
@limiter.limit("60/minute")
def record(request: Request, body: UsageEvent, db: Session = Depends(get_db)) -> Response:
    if not settings.usage_counts_enabled:
        raise HTTPException(status_code=404)
    # Dropped events get the same 204, so a crawler learns nothing from the answer.
    if _is_reader(request):
        stmt = insert(UsageCount).values(
            day=dt.datetime.now(dt.timezone.utc).date(), event=body.event, page_kind=body.page_kind, count=1
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["day", "event", "page_kind"], set_={"count": UsageCount.count + 1}
            )
        )
        db.commit()
    return Response(status_code=204)


@router.get("/admin")
def readout(db: Session = Depends(get_db), _: str = Depends(require_admin)) -> dict:
    rows = db.execute(
        select(UsageCount).order_by(UsageCount.day.desc(), UsageCount.event, UsageCount.page_kind)
    ).scalars()
    return {
        "rows": [
            {"day": r.day.isoformat(), "event": r.event, "page_kind": r.page_kind, "count": r.count} for r in rows
        ]
    }
