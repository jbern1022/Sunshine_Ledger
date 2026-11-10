"""Record format and validation for evidence-linked news analysis (rubric v1).

Todoist 6hrmjg4P4vHP9cGp; rubric and protocol in docs/NEWS_ANALYSIS_SCHEMA.md.

This module defines what a single analysis of one article about one bill may contain and
rejects anything the rubric forbids. It does not call a model and stores nothing. Rules that
matter, each enforced below:

* Tone and stance are separate. A record can carry a tone without any stance, and nothing
  here derives one from the other.
* A stance other than "insufficient_evidence" needs at least one supporting passage that
  appears verbatim in the article text at the stated offsets, and a speaker.
* A stance is about the narrator (the article's own voice) or a quoted speaker. A quoted speaker
  needs a name. The narrator never gets the stance of someone they quote.
* Headline-only text can carry a tone and descriptive stances only, and cannot carry arguments.
  It must be marked so (`text_scope`).
* Every record states that it is a model estimate, with its rubric and method versions. There
  is no numeric confidence: an unsupported claim is "insufficient_evidence" or is abstained.
"""

from __future__ import annotations

from dataclasses import dataclass, field

RUBRIC_VERSION = "news_rubric/1"

STANCES = ("supports", "opposes", "mixed", "descriptive", "insufficient_evidence")
TONES = ("negative", "neutral", "positive", "mixed", "insufficient_evidence")
TEXT_SCOPES = ("full_text", "partial_text", "headline_only")
SPEAKER_ROLES = ("narrator", "quoted_speaker")


@dataclass(frozen=True)
class Passage:
    quote: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class Stance:
    speaker_role: str
    speaker_name: str | None
    label: str
    passages: tuple[Passage, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class Argument:
    text: str
    passage: Passage
    speaker_role: str
    speaker_name: str | None = None


@dataclass(frozen=True)
class Tone:
    label: str
    passages: tuple[Passage, ...] = ()
    rationale: str = ""


@dataclass(frozen=True)
class Target:
    bill_entity_id: str
    bill_text_version: str  # which version of the bill the article is judged against
    provision_ref: str | None = None  # a section, when the article is about one provision


@dataclass(frozen=True)
class Analysis:
    article_url: str
    article_text: str
    text_scope: str
    target: Target
    method_version: str
    tone: Tone | None = None
    stances: tuple[Stance, ...] = ()
    arguments: tuple[Argument, ...] = ()
    model_estimate: bool = True
    rubric_version: str = RUBRIC_VERSION
    abstained: str | None = None  # reason, when the analysis declined to label anything
    problems: list[str] = field(default_factory=list, compare=False)


def _passage_problems(p: Passage, text: str, where: str) -> list[str]:
    out = []
    if not p.quote.strip():
        out.append(f"{where}: empty passage")
    elif not (0 <= p.char_start < p.char_end <= len(text)):
        out.append(f"{where}: offsets outside the article text")
    elif text[p.char_start:p.char_end] != p.quote:
        out.append(f"{where}: the quote is not the article's text at those offsets")
    return out


def validate(a: Analysis) -> list[str]:
    """Every way this analysis breaks the rubric; empty when it is acceptable."""
    out: list[str] = []
    if a.rubric_version != RUBRIC_VERSION:
        out.append(f"rubric_version is {a.rubric_version}, expected {RUBRIC_VERSION}")
    if not a.model_estimate:
        out.append("model_estimate must be true: these are estimates, never facts")
    if a.text_scope not in TEXT_SCOPES:
        out.append(f"unknown text_scope {a.text_scope!r}")
    if not a.article_url.strip() or not a.method_version.strip():
        out.append("article_url and method_version are required")
    if not a.target.bill_entity_id or not a.target.bill_text_version:
        out.append("target needs a bill and the bill text version it was judged against")

    if a.abstained:
        if a.tone or a.stances or a.arguments:
            out.append("an abstained analysis carries no labels")
        return out

    if a.tone:
        if a.tone.label not in TONES:
            out.append(f"unknown tone {a.tone.label!r}")
        if a.tone.label != "insufficient_evidence" and a.text_scope != "headline_only" and not a.tone.passages:
            out.append("tone: a label other than insufficient_evidence needs a supporting passage")
        for i, p in enumerate(a.tone.passages):
            out += _passage_problems(p, a.article_text, f"tone passage {i}")

    seen: set[tuple[str, str | None]] = set()
    for i, s in enumerate(a.stances):
        where = f"stance {i}"
        if s.label not in STANCES:
            out.append(f"{where}: unknown label {s.label!r}")
        if s.speaker_role not in SPEAKER_ROLES:
            out.append(f"{where}: unknown speaker_role {s.speaker_role!r}")
        if s.speaker_role == "quoted_speaker" and not (s.speaker_name or "").strip():
            out.append(f"{where}: a quoted speaker needs a name")
        if s.speaker_role == "narrator" and s.speaker_name:
            out.append(f"{where}: the narrator has no speaker_name")
        key = (s.speaker_role, s.speaker_name)
        if key in seen:
            out.append(f"{where}: a second stance for the same speaker; use 'mixed'")
        seen.add(key)
        if s.label not in ("insufficient_evidence",) and not s.passages:
            out.append(f"{where}: needs at least one supporting passage")
        if not s.rationale.strip() and s.label != "insufficient_evidence":
            out.append(f"{where}: needs a rationale")
        if a.text_scope == "headline_only" and s.label not in ("descriptive", "insufficient_evidence"):
            out.append(f"{where}: a headline alone cannot support {s.label!r}")
        for j, p in enumerate(s.passages):
            out += _passage_problems(p, a.article_text, f"{where} passage {j}")

    if a.text_scope == "headline_only" and a.arguments:
        out.append("arguments cannot be extracted from a headline alone")
    for i, arg in enumerate(a.arguments):
        where = f"argument {i}"
        if not arg.text.strip():
            out.append(f"{where}: empty")
        if arg.speaker_role not in SPEAKER_ROLES:
            out.append(f"{where}: unknown speaker_role {arg.speaker_role!r}")
        if arg.speaker_role == "quoted_speaker" and not (arg.speaker_name or "").strip():
            out.append(f"{where}: a quoted speaker needs a name")
        out += _passage_problems(arg.passage, a.article_text, f"{where} passage")
    return out
