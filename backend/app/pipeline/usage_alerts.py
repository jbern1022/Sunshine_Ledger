"""Warn before the monthly LegiScan limit runs out.

Run after the nightly LegiScan step: when this month's recorded calls pass
70% and then 90% of settings.legiscan_monthly_limit, post one ntfy message
each (to settings.ntfy_alert_url, the topic Kuma already notifies). An
early warning, not a hard stop: the nightly cap still bounds each night.

The last level alerted is kept in source_checks ("legiscan_usage_alert",
e.g. "2026-10:70"), so each level alerts once a month.

    python -m app.pipeline.usage_alerts
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SourceCheck
from app.pipeline.legiscan import month_start, month_to_date
from app.pipeline.source_checks import record_check

logger = logging.getLogger(__name__)

LEVELS = (90, 70)  # highest first
ALERT_KEY = "legiscan_usage_alert"


def _send(message: str) -> None:
    if not settings.ntfy_alert_url:
        logger.warning("NTFY_ALERT_URL not set; alert only logged: %s", message)
        return
    httpx.post(
        settings.ntfy_alert_url,
        content=message.encode(),
        headers={"Title": "Sunshine Ledger: LegiScan usage", "Tags": "warning"},
        timeout=10.0,
    ).raise_for_status()


def check_monthly_usage(db: Session, *, send=_send) -> int | None:
    """Alert if this month's calls crossed a level not yet alerted.
    Returns the level alerted (70 or 90), or None."""
    used = month_to_date(db)
    limit = settings.legiscan_monthly_limit
    month = month_start().strftime("%Y-%m")
    level = next((lvl for lvl in LEVELS if used >= limit * lvl / 100), None)
    if level is None:
        return None

    last = db.execute(select(SourceCheck.last_result).where(SourceCheck.source_key == ALERT_KEY)).scalar()
    last_month, _, last_level = (last or "").partition(":")
    if last_month == month and last_level.isdigit() and int(last_level) >= level:
        return None

    try:
        send(
            f"LegiScan calls this month: {used:,} of {limit:,} ({level}%+). "
            f"Nightly cap is {settings.legiscan_nightly_call_budget}/night. "
            "Check the LegiScan dashboard (it also counts cache hits)."
        )
    except Exception as exc:  # noqa: BLE001 -- not recorded, so the next run tries again
        logger.warning("LegiScan usage alert not sent: %s", exc)
        return None
    record_check(db, ALERT_KEY, f"{month}:{level}")
    return level


if __name__ == "__main__":
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session = SessionLocal()
    try:
        level = check_monthly_usage(session)
        print(f"LegiScan usage alert: {f'{level}% sent' if level else 'none'} ({month_to_date(session):,} calls this month)")
    finally:
        session.close()
