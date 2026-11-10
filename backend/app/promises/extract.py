"""Verbatim statement extraction (Todoist 6hvxrjMqXGM5QfWp).

The local model proposes passages that read like commitments. We keep a
passage only if it appears, character for character, in the snapshot's text
(see snapshot_text.py); anything the model paraphrased or invented is dropped
and counted. What is stored and shown as the promise is that exact text, with
the offsets, the source URL and the capture time. The model's labels
(commitment vs. value statement, topics) are drafts, stored under
`auto_labels` and always labelled automated. No fulfillment status exists.

Usage (needs Ollama; on the Mac, not in Docker):
    python -m app.promises.extract [--limit N]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import OfficialSite, PromiseItem, SiteSnapshot
from app.pipeline.summarize import OllamaClient
from app.pipeline.topic_tagging_seed import TAGS
from app.promises.snapshot_text import TEXT_VERSION, snapshot_text

logger = logging.getLogger(__name__)

PROMPT_VERSION = "promises-extract-v1"
TOPIC_SLUGS = [slug for slug, _ in TAGS]
COMMITMENT_TYPES = ("commitment", "value_statement", "other")
MIN_QUOTE, MAX_QUOTE = 25, 700
CHUNK_CHARS = 3500

PROMPT = """You are helping a nonprofit that records what elected officials and candidates say they will do, in their own words.

Below is text from a page the candidate published. Find sentences or short passages in which the author states something they will do, plan to do, or are working toward (a commitment), or states a value or priority (a value statement).

Rules:
- Copy each passage EXACTLY as written, character for character. Do not paraphrase, shorten, fix spelling or merge sentences.
- Only passages by the author about their own intentions. Skip biography, praise of others, attacks on opponents, event notices, donation requests and boilerplate.
- If there are none, return {{"items": []}}.

Return JSON only: {{"items": [{{"quote": "<exact text>", "type": "commitment" or "value_statement", "topics": [zero or more of: {topics}]}}]}}

TEXT:
{text}
"""


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split at line boundaries so a quote is never cut in the middle."""
    out, cur, n = [], [], 0
    for line in text.split("\n"):
        if n + len(line) > size and cur:
            out.append("\n".join(cur))
            cur, n = [], 0
        cur.append(line)
        n += len(line) + 1
    if cur:
        out.append("\n".join(cur))
    return out


def parse_items(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    items = data.get("items") if isinstance(data, dict) else data
    return [i for i in items if isinstance(i, dict) and isinstance(i.get("quote"), str)] if isinstance(items, list) else []


def locate(text: str, quote: str, taken: set[tuple[int, int]]) -> tuple[int, int] | None:
    """Offsets of `quote` in `text`, exact match only, skipping spans already
    claimed (the same sentence quoted twice on a page is two places)."""
    start = text.find(quote)
    while start != -1:
        span = (start, start + len(quote))
        if span not in taken:
            return span
        start = text.find(quote, start + 1)
    return None


def extract_snapshot(db: Session, snap: SiteSnapshot, body: bytes, client, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    text = snapshot_text(body)
    stats = {"proposed": 0, "kept": 0, "rejected_not_found": 0, "rejected_length": 0, "duplicate": 0}
    taken = {(i.char_start, i.char_end) for i in snap.items}
    winner_id = snap.site.winner_id
    for part in chunks(text):
        raw = client.generate(PROMPT.format(topics=", ".join(TOPIC_SLUGS), text=part), json_mode=True)
        for item in parse_items(raw):
            stats["proposed"] += 1
            quote = item["quote"]
            if not (MIN_QUOTE <= len(quote) <= MAX_QUOTE):
                stats["rejected_length"] += 1
                continue
            span = locate(text, quote, set())
            if span is None:
                stats["rejected_not_found"] += 1
                continue
            if span in taken:
                span = locate(text, quote, taken)
                if span is None:
                    stats["duplicate"] += 1
                    continue
            taken.add(span)
            ctype = item.get("type") if item.get("type") in COMMITMENT_TYPES else "other"
            topics = [t for t in (item.get("topics") or []) if t in TOPIC_SLUGS]
            db.add(
                PromiseItem(
                    snapshot_id=snap.id,
                    winner_id=winner_id,
                    quote_text=text[span[0]:span[1]],
                    char_start=span[0],
                    char_end=span[1],
                    source_url=snap.url,
                    captured_at=snap.fetched_at,
                    auto_labels={
                        "automated": True,
                        "commitment_type": ctype,
                        "topics": topics,
                        "model": getattr(client, "model", "unknown"),
                        "prompt_version": PROMPT_VERSION,
                    },
                    review_state="unreviewed",
                )
            )
            stats["kept"] += 1
    snap.extracted_at = now
    snap.extracted_text_version = TEXT_VERSION
    db.flush()
    return stats


def verify_item(item: PromiseItem, body: bytes) -> bool:
    """True when the stored quote is still exactly what the snapshot says at
    its offsets. Run as an audit; a False means the extractor or the text
    function changed and the item must be re-extracted, not trusted."""
    return snapshot_text(body)[item.char_start:item.char_end] == item.quote_text


def pending_snapshots(db: Session, limit: int | None = None) -> list[SiteSnapshot]:
    stmt = (
        select(SiteSnapshot)
        .join(OfficialSite, OfficialSite.id == SiteSnapshot.site_id)
        .where(SiteSnapshot.status == "ok", SiteSnapshot.extracted_at.is_(None))
        .order_by(SiteSnapshot.fetched_at)
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars())


def run(db: Session, client, *, limit: int | None = None, storage_dir: str | None = None) -> dict:
    root = Path(storage_dir or settings.snapshot_dir)
    totals = {"snapshots": 0, "kept": 0, "rejected_not_found": 0, "proposed": 0}
    for snap in pending_snapshots(db, limit):
        body = (root / snap.storage_path).read_bytes()
        s = extract_snapshot(db, snap, body, client)
        db.commit()
        totals["snapshots"] += 1
        for k in ("kept", "rejected_not_found", "proposed"):
            totals[k] += s[k]
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    client = OllamaClient(model=settings.ollama_layers_model, temperature=0, num_predict=2048, seed=42)
    with SessionLocal() as db:
        logger.info("extract: %s", run(db, client, limit=args.limit))


if __name__ == "__main__":
    main()
