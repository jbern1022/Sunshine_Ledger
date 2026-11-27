"""'What legislative staff say this does' (Todoist 6j5J3C8qGR8XwgGG).

The latest staff analysis's own words, not a model's: the "Effect of Proposed
Changes" and fiscal impact sections, cut out by the same patterns the layer
pipeline uses (app.pipeline.bill_layers_text). Only the layout changes: PDF
line wraps are joined into paragraphs, the PDF's private-use bullet glyph
becomes "•", the running page header ("CS/CS/HB 1389") is dropped, and
footnotes, which the PDF prints mid-sentence at each page break, are moved to
a Notes list at the end. Every other word, number and footnote marker is kept.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import StaffAnalysis
from app.pipeline.bill_layers_text import extract_effect_section, extract_fiscal_section

# Long enough for HB 1389's 9,700-char effect section; a longer one is cut at a
# paragraph break and says so, with the PDF linked for the rest.
MAX_CHARS = 20_000
_BULLETS = re.compile(r"^[•▪●\-–]\s*")
_SENTENCE_END = re.compile(r"[.:;?!)\]]$")
_HEADING_MAX = 60


# The running page header: the bill number alone on a line.
_PAGE_HEADER = re.compile(
    r"^(?:(?:CS/)*(?:ENG/)?(?:HB|SB|HJR|SJR|HM|SM|HR|SR|HCR|SCR|PCB|PCS)\s*\d+[A-Z]?"
    r"|BILL:\s.*Page\s+\d+|Page\s+\d+(?:\s+of\s+\d+)?)$"
)
# A footnote: its number, a space, then a capital, a quote or a citation lead.
_FOOTNOTE = re.compile(r"^(\d{1,3})\s+(?=[A-Z\u201c\"]|s\.\s|ss\.\s|ch\.\s|art\.\s)")
NOTES_HEADING = "Notes"


def tidy(section: str) -> str:
    """Join PDF line wraps into paragraphs; keep bullets and short headings
    on their own lines; drop page headers; move footnotes to the end."""
    paragraphs: list[str] = []
    notes: list[str] = []
    in_note = False
    prev = ""
    for raw in section.splitlines():
        line = raw.strip()
        if not line:
            prev = ""
            in_note = False
            continue
        if _PAGE_HEADER.match(line):
            in_note = False  # the footnotes of a page end at the next page's header
            continue
        note = _FOOTNOTE.match(line)
        if note:
            notes.append(f"[{note.group(1)}] {line[note.end():]}")
            in_note = True
            continue
        if in_note:
            # A wrapped footnote continues; a finished one followed by a
            # capitalised line is the body resuming (no page header between).
            if not (_SENTENCE_END.search(notes[-1]) and line[:1].isupper()):
                notes[-1] += " " + line
                continue
            in_note = False
        bullet = _BULLETS.match(line)
        if bullet:
            line = "• " + line[bullet.end():]
        starts_new = (
            not paragraphs
            or not prev
            or bool(bullet)
            or bool(_SENTENCE_END.search(prev))
            # a short unpunctuated line followed by a capital is a heading
            or (len(prev) <= _HEADING_MAX and line[:1].isupper())
        )
        if starts_new:
            paragraphs.append(line)
        else:
            paragraphs[-1] += " " + line
        prev = line
    if notes:
        paragraphs += [NOTES_HEADING, *notes]
    return "\n\n".join(paragraphs)


def _cut(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_CHARS:
        return text, False
    at = text.rfind("\n\n", 0, MAX_CHARS)
    return text[: at if at > 0 else MAX_CHARS], True


def staff_excerpt(db: Session, entity_id: uuid.UUID) -> dict | None:
    rows = db.execute(
        select(StaffAnalysis)
        .where(StaffAnalysis.entity_id == entity_id, StaffAnalysis.text.isnot(None), StaffAnalysis.text != "")
        .order_by(StaffAnalysis.analysis_date.desc().nulls_last(), StaffAnalysis.created_at.desc())
    ).scalars().all()
    if not rows:
        return None
    # Committees revise their analyses; the latest one that has either
    # section is shown, and the page says which version it is.
    for a in rows:
        effect = extract_effect_section(a.text)
        fiscal = extract_fiscal_section(a.text)
        if effect or fiscal:
            effect_text, effect_cut = _cut(tidy(effect)) if effect else (None, False)
            fiscal_text, fiscal_cut = _cut(tidy(fiscal)) if fiscal else (None, False)
            return {
                "committee": a.committee,
                "analysis_date": a.analysis_date,
                "source_url": a.source_url,
                "effect": effect_text,
                "fiscal": fiscal_text,
                "truncated": effect_cut or fiscal_cut,
                "analyses_count": len(rows),
                "is_latest": a is rows[0],
            }
    return None
