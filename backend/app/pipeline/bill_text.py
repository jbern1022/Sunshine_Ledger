"""Fetch and clean real bill text, replacing the thin `description` blurb as
summarization input (Roadmap).

Two sources, two retrieval paths, one cleaner:

- **LegiScan** (state bills) returns documents base64-encoded from a text
  API, as either PDF or HTML.
- **Legistar** (Jacksonville) has no text endpoint at all --
  `/Matters/{id}/Texts` returns 405 -- so the ordinance has to be picked out
  of the matter's attachment list, where it sits among exhibits under a name
  like "2026-646 - Original Bill".

LegiScan's documents come in two formats and both need cleaning before a
model sees them:

- PDFs of the filed bill, laid out for print. Every content line carries a
  *trailing* line number, and each page repeats a chamber header, a CODING
  legend, a document id and a page marker.
- HTML documents (roughly half the Florida corpus, Senate resolutions
  especially), which number lines at the *start* and carry a drafting
  stamp instead of per-page furniture.

Feeding either raw to a model wastes context on furniture and invites it
to quote line numbers back.

This module only fetches and stores. `summarize_batch.summarization_input`
decides what the model actually reads, and prefers `full_text` where it
exists -- a preference that passed the Roadmap's Step 2 quality gate before
being switched on (see docs and the ticket history). Storing text here is
enough to make a bill eligible for re-summarization: full text changes the
input hash, so the batch job picks it up on its own.
"""

from __future__ import annotations

import base64
import io
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.logging_setup import quiet_http_logging
from app.models import Bill, Entity
from app.pipeline.legiscan import LegiScanClient
from app.pipeline.text_cleanup import strip_page_artifacts

logger = logging.getLogger(__name__)

# Page furniture that repeats on every page of a filed bill.
_BOILERPLATE = re.compile(
    r"^\s*(?:"
    r"CODING:.*"                          # "CODING: Words stricken are deletions..."
    r"|Page \d+ of \d+"
    r"|(?:[A-Za-z]\s+){3,}[A-Za-z]\s*"    # letter-spaced "F L O R I D A  H O U S E ..."
    r"|[a-z]{1,4}\d+-\d+"                 # document ids like "hb95-00"
    r"|(?:CS/)?(?:HB|SB|HR|SR|HJR|SJR)\s*\d+\s+\d{4}"  # running header "HB 95  2026"
    r")\s*$",
    re.IGNORECASE,
)

# Trailing line number on a content line, e.g. "...effective date. 9". The
# separator is usually whitespace, but pypdf sometimes glues the number
# straight onto a hyphenated *word* ("Phelan-32"), so a hyphen counts too --
# but only when it follows a letter. A hyphen following a digit is a real
# citation ("chapter 2026-12", "s. 316-1"), not a broken word, and must not
# be treated as a separator. `match.start(1)` (not the whole match) is what
# gets sliced off below, so the hyphen itself survives.
_TRAILING_LINE_NUMBER = re.compile(r"(?:\s|(?<=[A-Za-z])-)(\d{1,3})\s*$")

# HTML bill text numbers lines at the START instead, e.g.
# "    2         A resolution designating February 3, 2026..."
# The trailing separator must be optional: bills contain numbered lines with
# no content ("    4  "), and those arrive here already rstripped. Requiring
# whitespace after the digits would fail to match them, break the expected
# sequence, and leave every following line's number embedded in the text.
_LEADING_LINE_NUMBER = re.compile(r"^\s*(\d{1,3})(?:\s|$)")

# Drafting stamp that appears once per HTML document, e.g.
# "8-02178-26                                            20261780__"
_DRAFT_STAMP = re.compile(r"^\s*\d+-\d+-\d+\s+\d+_*\s*$")


def clean_legislative_text(raw: str) -> str:
    """Strip print furniture from extracted bill-PDF text.

    Line numbers are only removed when they continue the expected sequence:
    the next line number found must be 1 to 3 more than the last one seen,
    which resyncs across a line that lost its own number in extraction
    without requiring the exact successor every time. A blunt "strip any
    trailing number" rule would corrupt real content -- statutory
    references, dollar amounts and dates routinely end a line -- so a
    false positive still requires a genuine coincidence with that narrow
    window, not just any nearby number.

    Pure function: no network, no DB, so the parsing rules stay testable
    without hitting LegiScan.
    """
    cleaned: list[str] = []
    expected = 0

    for line in raw.split("\n"):
        line = line.rstrip()
        if not line.strip() or _BOILERPLATE.match(line):
            continue

        match = _TRAILING_LINE_NUMBER.search(line)
        if match:
            # A missed line (blank, or one that didn't carry its number to
            # extracted text) can put the sequence briefly behind without
            # meaning the next number isn't real -- resync as long as it's
            # a small hop ahead rather than requiring the exact successor.
            #
            # Trade-off: the wider the window, the more real content it can
            # eat. With a window of 3, a line genuinely ending in a number
            # 1-3 above the last line number (e.g. "...subsection 14" read
            # right after line 12) is taken for a line number and stripped.
            # A window of 1 (exact successor only) never does that, but
            # then one missed number desyncs the rest of the page and
            # leaves every following line number in the text. 3 is the
            # smallest window that resynced every sample we checked.
            diff = int(match.group(1)) - expected
            if 1 <= diff <= 3:
                expected = int(match.group(1))
                line = line[: match.start(1)].rstrip()

        if line.strip():
            cleaned.append(line.strip())

    return "\n".join(cleaned)


def clean_html_legislative_text(raw: str) -> str:
    """Strip furniture from the text of an HTML bill document.

    Same job as `clean_legislative_text`, different layout: LegiScan's HTML
    documents number lines at the *start* rather than the end, and carry a
    drafting stamp instead of per-page headers. The sequential check is the
    same idea and exists for the same reason -- a line legitimately opening
    with a number ("2026 Regular Session...") must not lose it.
    """
    cleaned: list[str] = []
    expected = 0

    for line in raw.split("\n"):
        line = line.rstrip()
        if not line.strip() or _DRAFT_STAMP.match(line):
            continue

        match = _LEADING_LINE_NUMBER.match(line)
        if match and int(match.group(1)) == expected + 1:
            expected = int(match.group(1))
            line = line[match.end():]

        if line.strip():
            cleaned.append(line.strip())

    return "\n".join(cleaned)


def html_to_marked_text(html: str) -> str:
    """Turn LegiScan's Senate-style change markup into inline markers.

    Senate HTML marks deletions with `<s class="Remove">` and additions
    with `<u class="Insert">` (any tag carries the class -- some documents
    use `<span>` instead). Each such element is replaced with its text
    wrapped in `[deleted: ...]` / `[added: ...]` *before* the rest of the
    furniture-stripping runs, so those markers survive line cleaning intact
    instead of being flattened into indistinguishable plain text.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    def _wrap(css_class: str, kind: str) -> None:
        for el in soup.find_all(class_=css_class):
            raw = el.get_text()
            # Whitespace inside markers is single spaces (some Insert/Remove
            # spans hold only a run of whitespace -- an added or deleted
            # space -- which shouldn't produce an empty "[added: ]").
            text = " ".join(raw.split())
            if not text:
                el.replace_with(" " if raw else "")
                continue
            # An element's own leading/trailing whitespace is a word
            # boundary, so it stays OUTSIDE the marker: "of<u> receiving</u>"
            # must become "of [added: receiving]", not "of[added: receiving]"
            # (which law_as_amended would read as "ofreceiving").
            lead = " " if raw[:1].isspace() else ""
            trail = " " if raw[-1:].isspace() else ""
            el.replace_with(f"{lead}[{kind}: {text}]{trail}")

    _wrap("Remove", "deleted")
    _wrap("Insert", "added")

    return _merge_adjacent_markers(clean_html_legislative_text(soup.get_text()))


def extract_html_text(html_bytes: bytes) -> str:
    """Extract and clean text from an HTML bill document.

    Roughly half of LegiScan's Florida documents are served as text/html
    rather than PDF -- Senate resolutions especially. Treating those as
    unreadable would leave those bills falling back to the short blurb for
    no good reason.
    """
    return strip_page_artifacts(html_to_marked_text(html_bytes.decode("utf-8", errors="replace")))


# Two markers of the same kind separated only by whitespace -- or by
# nothing at all -- are one change that the source happened to split: a
# PDF word carrying a strike/underline that wrapped across a hard line break
# (one marker closes a line, the next opens the following one), or Senate
# HTML that wraps consecutive words in separate `<u class="Insert">`
# elements ("purpose of</u><u> receiving"). Fold those back into a single
# marker so a quote or search doesn't see it interrupted by "] [added: ".
#
# Exception: a marker that *opens* with a "Section N." heading keeps its own
# line, so law_as_amended still finds that heading at a line start.
_ADJACENT_MARKER = re.compile(
    r"\[(deleted|added): ([^\]]*)\]([ \t]*\n?[ \t]*)\[\1: (?!Section\s+\d+\.(?!\d))"
)


def _merge_adjacent_markers(text: str) -> str:
    def _join(match: re.Match[str]) -> str:
        kind, prefix, gap = match.group(1), match.group(2), match.group(3)
        if not gap:
            # Directly abutting ("aid][added: .]") -- no space was there.
            sep = ""
        elif "\n" in gap and prefix.rstrip().endswith("-"):
            # A hyphenated word broken across the line ("Tatton-Brown-" /
            # "Rahman") continues with no space.
            sep = ""
        else:
            sep = " "
        return f"[{kind}: {prefix.rstrip()}{sep}"

    while True:
        new_text = _ADJACENT_MARKER.sub(_join, text)
        if new_text == text:
            return new_text
        text = new_text


def mark_words(
    words: list[dict], segments: list[dict], *, margin_x: float = 60.0
) -> list[str]:
    """Reassemble pdfplumber words into text lines with change markers.

    A pure function over pdfplumber-style dicts (`words` need `text, x0,
    x1, top, bottom`; `segments` -- the thin rules a PDF viewer renders as
    strike-through/underline -- need `x0, x1, top, bottom`) so the layout
    rules are testable without opening a PDF.

    Words are grouped into lines by `top` (within 2pt) and then put in
    reading order by `x0`: an underlined word can sit a fraction of a point
    higher than its unmarked neighbours, so ordering by `top` alone would
    pull it to the front of its line (H1171 came out as
    "[added: This act ...] Section 1."). Left-margin line numbers are
    dropped by position rather than pattern-matched after the fact, and
    each word is classified by whether segments crossing its vertical
    middle (struck) or running along its bottom (underlined/added) cover at
    least half of its width -- summed across however many segments touch
    it, so a rule that merely grazes a word's edge (e.g. a neighbor's
    underline overrunning by a point or two) doesn't pull an unrelated word
    into the marker. Consecutive words of the same kind become one marker.

    A word may also carry its pdfplumber `chars` (`extract_words(
    return_chars=True)`). When its characters disagree -- a renumbering
    such as "2.1." where "2." is underlined and "1." struck, printed with
    no space between -- the word is split where the classification
    changes, giving "[added: 2.][deleted: 1.]" rather than one marker (or
    none) over both numbers.
    """
    # Only thin, roughly-horizontal marks count as strike/underline rules --
    # a tall page-margin rule (drawn as a rect spanning the whole column)
    # would otherwise need to be excluded by never overlapping any word, but
    # filtering it out up front is cheaper and more obviously correct.
    thin_segments = [s for s in segments if abs(s["bottom"] - s["top"]) <= 5]

    def _classify(box: dict) -> str | None:
        width = box["x1"] - box["x0"]
        if width <= 0:
            return None
        mid = (box["top"] + box["bottom"]) / 2
        bottom = box["bottom"]
        deleted_coverage = added_coverage = 0.0
        for seg in thin_segments:
            overlap = min(seg["x1"], box["x1"]) - max(seg["x0"], box["x0"])
            if overlap <= 0:
                continue  # no horizontal overlap with this box
            center = (seg["top"] + seg["bottom"]) / 2
            if abs(center - mid) <= 2.5:
                deleted_coverage += overlap
            elif 0 <= center - bottom <= 3:
                added_coverage += overlap
        if deleted_coverage / width >= 0.5:
            return "deleted"
        if added_coverage / width >= 0.5:
            return "added"
        return None

    def _pieces(word: dict) -> list[tuple[str | None, str]]:
        """(kind, text) pieces of one word -- usually just one."""
        chars = [c for c in word.get("chars") or [] if c.get("text", "").strip()]
        if chars:
            kinds = [_classify(c) for c in chars]
            # Split only on a genuine struck/underlined disagreement. A word
            # whose characters are merely partly covered (a short rule under
            # "syndrome;" missing the ";") keeps its whole-word verdict, so
            # punctuation doesn't spill outside a marker.
            if "deleted" in kinds and "added" in kinds:
                pieces: list[tuple[str | None, str]] = []
                for char, kind in zip(chars, kinds):
                    if pieces and pieces[-1][0] == kind:
                        pieces[-1] = (kind, pieces[-1][1] + char["text"])
                    else:
                        pieces.append((kind, char["text"]))
                return pieces
        return [(_classify(word), word["text"])]

    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - lines[-1][0]["top"]) <= 2:
            lines[-1].append(word)
        else:
            lines.append([word])

    result: list[str] = []
    for line_words in lines:
        line_words.sort(key=lambda w: w["x0"])
        kept = [
            w
            for w in line_words
            if not (w["x0"] < margin_x and w["text"].strip().isdigit())
        ]

        # Runs of same-kind text; `glued` means no space before the run
        # (the run continues the previous word, split by classification).
        runs: list[tuple[str | None, str, bool]] = []
        for w in kept:
            for i, (kind, text) in enumerate(_pieces(w)):
                glued = i > 0
                if runs and runs[-1][0] == kind:
                    prev_kind, prev_text, prev_glued = runs[-1]
                    runs[-1] = (kind, prev_text + ("" if glued else " ") + text, prev_glued)
                else:
                    runs.append((kind, text, glued))

        out = ""
        for kind, text, glued in runs:
            piece = f"[{kind}: {text}]" if kind else text
            out += piece if (glued or not out) else " " + piece
        result.append(out)

    return result


def _extract_pdf_text_pypdf(pdf_bytes: bytes) -> str:
    """Fallback PDF extraction: whole-page text, no change markers.

    Used when pdfplumber can't open or parse a document at all -- rare, but
    better to fall back to the old (marker-less) behavior than to fail the
    whole fetch.
    """
    from pypdf import PdfReader  # imported lazily -- only bill-text runs need it

    reader = PdfReader(io.BytesIO(pdf_bytes))
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    # strip_page_artifacts runs first, on the raw text, where every line
    # still carries its number: it recognises whole runs even when a page
    # restarts its numbering at 1 (Jacksonville ordinances), which
    # clean_legislative_text's forward-only window can't follow. It also
    # removes page headers _BOILERPLATE doesn't know.
    return clean_legislative_text(strip_page_artifacts(raw))


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract and clean text from a bill PDF, with inline change markers.

    House PDFs draw strike-through and underline as thin rules rather than
    encoding them in the text, so pypdf's plain `extract_text()` flattens a
    deletion and its replacement together (e.g. "An No agency"). pdfplumber
    exposes both the words and the rules as positioned objects, which
    `mark_words` turns back into `[deleted: ...]` / `[added: ...]` markers.

    Falls back to the pypdf path (no markers, but readable) if pdfplumber
    can't process the document -- one malformed PDF shouldn't take down a
    backfill.
    """
    try:
        import pdfplumber  # imported lazily -- only bill-text runs need it

        lines: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                words = page.extract_words(return_chars=True)
                segments = list(page.lines) + list(page.rects)
                lines.extend(mark_words(words, segments))
                # pdfplumber caches every parsed layout object on the page
                # until the document closes; releasing each page as we go
                # took a 100-page House bill (H5003) from ~607 MB to
                # ~107 MB peak with identical output.
                page.close()
    except Exception:
        logger.warning("pdfplumber extraction failed -- falling back to pypdf", exc_info=True)
        return _extract_pdf_text_pypdf(pdf_bytes)

    kept = [line for line in lines if line.strip() and not _BOILERPLATE.match(line)]
    # Strip page headers before merging markers, so an [added: ...] block
    # split by a page break ("...coordination.]\nhb565 -02-er\n[added: c. ...")
    # is folded back into one.
    return _merge_adjacent_markers(strip_page_artifacts("\n".join(kept)))


def fetch_bill_text(client: LegiScanClient, doc_id: int) -> str | None:
    """Fetch one document by LegiScan doc_id and return its cleaned text.

    Returns None for document types we can't read rather than raising --
    LegiScan serves some documents as HTML or Word, and one unreadable
    document shouldn't stop a backfill.
    """
    doc = client._call("getBillText", id=str(doc_id))["text"]
    mime = doc.get("mime")
    raw = base64.b64decode(doc["doc"])

    if mime == "application/pdf":
        return extract_pdf_text(raw)
    if mime in ("text/html", "application/html"):
        return extract_html_text(raw)

    logger.warning("doc_id=%s has unsupported mime %s -- skipping", doc_id, mime)
    return None


# Legistar exposes the ordinance itself as one attachment among several
# exhibits, distinguished only by name -- "2026-646 - Original Bill",
# "2026-662 Original Bill". Punctuation and spacing vary between records, so
# match on the phrase rather than an exact title.
_ORIGINAL_BILL = re.compile(r"original\s+bill", re.IGNORECASE)


def fetch_legistar_bill_text(client_name: str, matter_id: int, *, timeout: float = 90.0) -> str | None:
    """Cleaned text of a Legistar matter's "Original Bill" attachment.

    Legistar has no text endpoint (`/Matters/{id}/Texts` returns 405), so the
    bill itself has to be pulled from the attachment list. Exhibits are
    deliberately skipped: they're supporting material (maps, agreements,
    budget tables) rather than the legislation, and folding them in would
    dilute the summarization input rather than enrich it.

    Returns None when no Original Bill attachment exists, which is normal --
    some matters are procedural and carry only exhibits.
    """
    import httpx

    base = f"https://webapi.legistar.com/v1/{client_name}"
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        attachments = client.get(f"{base}/Matters/{matter_id}/Attachments").json()
        original = next(
            (a for a in attachments if _ORIGINAL_BILL.search(a.get("MatterAttachmentName") or "")),
            None,
        )
        if original is None:
            return None

        link = original.get("MatterAttachmentHyperlink")
        if not link:
            return None

        resp = client.get(link)
        resp.raise_for_status()

    if not resp.content.startswith(b"%PDF"):
        logger.warning("Legistar attachment for matter %s is not a PDF -- skipping", matter_id)
        return None

    # Deliberately the pypdf path (no change markers), not extract_pdf_text.
    # Jacksonville ordinances are laid out unlike Florida House bills:
    # italic/bold runs sit in boxes shifted a point or two off the baseline,
    # so pdfplumber's top-based line grouping scrambles and splits lines;
    # underlines are read as strike-throughs (e.g. "shall not be construed"
    # came back as [deleted: ...]); and the signature-block rules mark whole
    # lines. Switching Legistar to the marker extractor needs a
    # baseline-aware line grouping first, tested against Legistar fixtures.
    return _extract_pdf_text_pypdf(resp.content)


def _legistar_text_for(entity: Entity) -> str | None:
    """Fetch (without storing) the current text for one Legistar bill."""
    ids = entity.external_ids or {}
    matter_id, client_name = ids.get("legistar_matter_id"), ids.get("legistar_client")
    if not matter_id or not client_name:
        return None
    return fetch_legistar_bill_text(client_name, int(matter_id))


def backfill_legistar_texts(db: Session, *, limit: int | None = None, refresh: bool = False) -> tuple[int, int]:
    """Populate `bills.full_text` for Legistar-sourced bills.

    Separate from the LegiScan backfill because the retrieval path is
    entirely different -- attachment list rather than a text API -- though
    both end up in the same PDF cleaner.

    Returns (fetched, skipped_or_failed).
    """
    stmt = (
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill", Bill.source_system == "legistar")
        .options(selectinload(Entity.bill))
    )
    entities = [
        e for e in db.execute(stmt).scalars().all() if refresh or not (e.bill and e.bill.full_text)
    ]
    if limit:
        entities = entities[:limit]

    logger.info("Fetching Legistar bill text for %d bills", len(entities))

    fetched = failed = 0
    for entity in entities:
        matter_id = (entity.external_ids or {}).get("legistar_matter_id")
        try:
            text = _legistar_text_for(entity)
            if not text:
                failed += 1
                continue
            entity.bill.full_text = text
            db.commit()
            fetched += 1
        except Exception as exc:  # noqa: BLE001 -- one bad attachment shouldn't kill the backfill
            db.rollback()
            failed += 1
            logger.warning("Legistar text fetch failed for matter %s: %s", matter_id, exc)

    logger.info("Legistar bill text: %d fetched, %d skipped/failed", fetched, failed)
    return fetched, failed


def _legiscan_text_for(client: LegiScanClient, entity: Entity) -> str | None:
    """Fetch (without storing) the current text for one LegiScan bill."""
    legiscan_id = (entity.external_ids or {}).get("legiscan_id")
    if not legiscan_id:
        return None
    docs = client.get_bill(int(legiscan_id)).get("texts") or []
    if not docs:
        return None
    # Last entry is the most recent version (LegiScan orders them
    # oldest-first), which is what should be summarized.
    return fetch_bill_text(client, int(docs[-1]["doc_id"]))


def backfill_bill_texts(db: Session, *, limit: int | None = None, refresh: bool = False) -> tuple[int, int]:
    """Populate `bills.full_text` for LegiScan bills that don't have it.

    One `getBillText` call per bill, so it spends real API quota (free tier
    is 30,000/month against ~1,900 state bills) -- hence skipping bills that
    already have text unless `refresh` is set.

    Returns (fetched, skipped_or_failed).
    """
    client = LegiScanClient()

    stmt = (
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill", Bill.source_system == "legiscan")
        .options(selectinload(Entity.bill))
    )
    entities = [
        e for e in db.execute(stmt).scalars().all() if refresh or not (e.bill and e.bill.full_text)
    ]
    if limit:
        entities = entities[:limit]

    logger.info("Fetching bill text for %d bills", len(entities))

    fetched = failed = 0
    for entity in entities:
        bill = entity.bill
        try:
            text = _legiscan_text_for(client, entity)
            if not text:
                failed += 1
                continue

            bill.full_text = text
            db.commit()
            fetched += 1
        except Exception as exc:  # noqa: BLE001 -- one bad bill shouldn't kill the backfill
            db.rollback()
            failed += 1
            logger.warning("Bill text fetch failed for %s: %s", bill.bill_number if bill else entity.id, exc)

    logger.info("Bill text: %d fetched, %d skipped/failed", fetched, failed)
    return fetched, failed


# A line-start bill section heading, same rule as bill_layers_text's
# `_BILL_SECTION` ("Section 316.1895" is a citation, not a heading).
_HEADING_LINE = re.compile(r"(?m)^\s*Section\s+\d+\.(?!\d)", re.IGNORECASE)
_DELETED_SPAN = re.compile(r"\[deleted: [^\]]*\]")
_NUMBER_ONLY_LINE = re.compile(r"(?m)^\s*\d+\s*$")

# Thresholds for flagging a re-extraction for a human look before it is
# written: a big length swing, text that is mostly "deleted", section
# headings that vanished, or left-margin line numbers leaking through.
COMPARE_MAX_LENGTH_CHANGE = 0.15
COMPARE_MAX_DELETED_PCT = 60.0


def clean_stored_text(text: str) -> str:
    """The cleanup new extractions get, applied to already-stored text:
    page headers and margin line numbers out, then any change markers the
    removed lines had split apart merged back together."""
    return _merge_adjacent_markers(strip_page_artifacts(text))


def clean_stored_texts(db: Session, *, apply: bool, limit: int | None = None) -> dict:
    """Run clean_stored_text over every stored bill text, without re-fetching.

    Dry run unless `apply`. Changed text changes each bill's summary and
    layer input hashes, so the nightly batch regenerates them on its own.
    """
    stmt = select(Bill).where(Bill.full_text.isnot(None)).order_by(Bill.bill_number)
    if limit:
        stmt = stmt.limit(limit)
    stats = {"checked": 0, "changed": 0, "chars_removed": 0}
    for bill in db.execute(stmt).scalars():
        stats["checked"] += 1
        cleaned = clean_stored_text(bill.full_text)
        if cleaned != bill.full_text:
            stats["changed"] += 1
            stats["chars_removed"] += len(bill.full_text) - len(cleaned)
            if apply:
                bill.full_text = cleaned
    if apply:
        db.commit()
    return stats


def compare_texts(old: str, new: str) -> dict:
    """Compare a bill's stored text with a fresh re-extraction.

    Pure function behind `--compare`. Lengths and heading counts are taken
    on the law-as-amended view, so the markers themselves don't count as a
    change; the deleted share is measured on the new marked text.
    """
    from app.pipeline.bill_layers_text import law_as_amended

    old_amended, new_amended = law_as_amended(old or ""), law_as_amended(new or "")
    old_len, new_len = len(old_amended), len(new_amended)
    length_ratio = new_len / old_len if old_len else None

    deleted_chars = sum(len(m) for m in _DELETED_SPAN.findall(new or ""))
    deleted_pct = 100.0 * deleted_chars / len(new) if new else 0.0

    old_headings = len(_HEADING_LINE.findall(old_amended))
    new_headings = len(_HEADING_LINE.findall(new_amended))
    number_only_lines = len(_NUMBER_ONLY_LINE.findall(new or ""))

    reasons: list[str] = []
    if length_ratio is None:
        if new_len:
            reasons.append("length")
    elif abs(length_ratio - 1) > COMPARE_MAX_LENGTH_CHANGE:
        reasons.append("length")
    if deleted_pct > COMPARE_MAX_DELETED_PCT:
        reasons.append("deleted")
    if new_headings < old_headings:
        reasons.append("headings")
    if number_only_lines > 0:
        reasons.append("numbers")

    return {
        "old_len": old_len,
        "new_len": new_len,
        "length_ratio": length_ratio,
        "deleted_pct": deleted_pct,
        "old_headings": old_headings,
        "new_headings": new_headings,
        "number_only_lines": number_only_lines,
        "flag": bool(reasons),
        "reasons": reasons,
    }


def compare_bill_texts(db: Session, *, source: str = "legiscan", limit: int | None = None) -> list[dict]:
    """Re-extract stored bills' text WITHOUT writing it, and compare.

    Only bills that already have `full_text` are considered (there is
    nothing to compare otherwise). Returns one row per bill:
    `compare_texts(...)` plus `bill_number`, or `error` if the fetch failed.
    """
    sources = ("legiscan", "legistar") if source == "all" else (source,)
    stmt = (
        select(Entity)
        .join(Bill, Bill.entity_id == Entity.id)
        .where(Entity.entity_type == "bill", Bill.source_system.in_(sources))
        .options(selectinload(Entity.bill))
    )
    entities = [e for e in db.execute(stmt).scalars().all() if e.bill and e.bill.full_text]
    if limit:
        entities = entities[:limit]

    legiscan_client = LegiScanClient() if "legiscan" in sources else None
    rows: list[dict] = []
    for entity in entities:
        bill = entity.bill
        try:
            if bill.source_system == "legistar":
                new = _legistar_text_for(entity)
            else:
                new = _legiscan_text_for(legiscan_client, entity)
        except Exception as exc:  # noqa: BLE001 -- report it, keep comparing
            rows.append({"bill_number": bill.bill_number, "error": str(exc)})
            continue
        if not new:
            rows.append({"bill_number": bill.bill_number, "error": "no text fetched"})
            continue
        rows.append({"bill_number": bill.bill_number, **compare_texts(bill.full_text, new)})
    return rows


def format_compare_rows(rows: list[dict]) -> str:
    header = f"{'BILL':<14} {'LEN_RATIO':>9} {'DELETED%':>8} {'HEADINGS':>9} {'NUM_LINES':>9}  FLAG"
    out = [header]
    for r in rows:
        if "error" in r:
            out.append(f"{r['bill_number']:<14} ERROR: {r['error']}")
            continue
        ratio = f"{r['length_ratio']:.2f}" if r["length_ratio"] is not None else "n/a"
        headings = f"{r['old_headings']}->{r['new_headings']}"
        flag = "FLAG " + ",".join(r["reasons"]) if r["flag"] else ""
        out.append(
            f"{r['bill_number']:<14} {ratio:>9} {r['deleted_pct']:>7.0f}% {headings:>9} "
            f"{r['number_only_lines']:>9}  {flag}"
        )
    return "\n".join(out)


if __name__ == "__main__":
    import argparse

    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    quiet_http_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true", help="Re-fetch bills that already have text.")
    parser.add_argument(
        "--source",
        choices=("legiscan", "legistar", "all"),
        default="legiscan",
        help="Which source system to backfill text for.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help=(
            "Re-extract bills that already have text WITHOUT writing it, and print "
            "old vs new stats per bill with a FLAG column (see compare_texts)."
        ),
    )
    parser.add_argument(
        "--clean-stored",
        action="store_true",
        help=(
            "Strip page headers and margin line numbers from already-stored text "
            "(no re-fetch). Dry run unless --apply."
        ),
    )
    parser.add_argument("--apply", action="store_true", help="With --clean-stored: write the cleaned text.")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.clean_stored:
            stats = clean_stored_texts(session, apply=args.apply, limit=args.limit)
            verb = "Cleaned" if args.apply else "Would clean"
            print(f"{verb} {stats['changed']} of {stats['checked']} bills "
                  f"({stats['chars_removed']:,} characters removed).")
            raise SystemExit(0)
        if args.compare:
            rows = compare_bill_texts(session, source=args.source, limit=args.limit)
            print(format_compare_rows(rows))
            flagged = sum(1 for r in rows if r.get("flag") or "error" in r)
            print(f"Compared {len(rows)} bills; {flagged} flagged or failed. Nothing was written.")
            raise SystemExit(0)
        ok = bad = 0
        if args.source in ("legiscan", "all"):
            a, b = backfill_bill_texts(session, limit=args.limit, refresh=args.refresh)
            ok, bad = ok + a, bad + b
        if args.source in ("legistar", "all"):
            a, b = backfill_legistar_texts(session, limit=args.limit, refresh=args.refresh)
            ok, bad = ok + a, bad + b
        print(f"Done: {ok} fetched, {bad} skipped/failed.")
    finally:
        session.close()
