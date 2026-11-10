"""Run the tone/stance/argument analysis of one article against one bill (rubric v1).

Takes a client with `generate(prompt, json_mode=True) -> str` (the same interface as the
Impact Lens mapper and the bill layers) and returns a validated `Analysis`. Nothing is stored and
no article is fetched here; the article text is an argument.

What the model is NOT trusted to do, and what this code does instead:

* Offsets: the model quotes passages; this code finds each quote in the article text itself and sets
  the offsets. A quote that is not in the text verbatim is dropped (never repaired or fuzzily matched).
* A stance, tone or argument whose passages all vanish is not kept as-is: a stance or tone becomes
  `insufficient_evidence`, an argument is dropped. This is the "reject unsupported target claims" rule.
* Headline-only text can only carry what the rubric allows; anything stronger is downgraded.
* The final record must pass `schema.validate`; if it cannot, `AnalysisError` is raised and nothing is
  published.
"""

from __future__ import annotations

import json

from app.news_analysis.schema import (
    RUBRIC_VERSION, STANCES, TONES, Analysis, Argument, Passage, Stance, Target, Tone, validate,
)

MAX_ATTEMPTS = 2
MAX_ARTICLE_CHARS = 12000


class AnalysisError(RuntimeError):
    pass


def build_prompt(article_text: str, text_scope: str, bill_name: str, bill_summary: str, provision_ref: str | None) -> str:
    target = f"the bill \"{bill_name}\"" + (f", specifically {provision_ref}" if provision_ref else "")
    return f"""You are labeling how one news article treats {target}.
What the bill does, in one sentence: {bill_summary}

Text scope: {text_scope}. {"Only a headline is given: do not infer an opinion from it." if text_scope == "headline_only" else ""}

Rules:
- Tone describes the article's OWN wording (negative, neutral, positive, mixed, insufficient_evidence). It is not stance.
- Stance is a speaker's position toward THIS bill: supports, opposes, mixed, descriptive, insufficient_evidence.
  Give one stance for the narrator (the article's own voice) and one for each quoted speaker, by name.
  A quotation is not the narrator's view. Negative reporting about a problem is not opposition to the bill.
- Every label other than insufficient_evidence needs "passages": exact quotes copied character for character from the article, and a one-sentence "rationale".
- "arguments": reasons a speaker gives, each with one exact quote and the speaker.
- If you cannot tell, use insufficient_evidence. Do not guess. Do not add reasons the text does not state.

Return JSON only:
{{"tone": {{"label": "...", "passages": ["exact quote"], "rationale": "..."}},
 "stances": [{{"speaker_role": "narrator" or "quoted_speaker", "speaker_name": null or "Name", "label": "...", "passages": ["exact quote"], "rationale": "..."}}],
 "arguments": [{{"text": "...", "quote": "exact quote", "speaker_role": "narrator" or "quoted_speaker", "speaker_name": null or "Name"}}]}}

ARTICLE:
{article_text[:MAX_ARTICLE_CHARS]}
"""


def _locate(text: str, quote: object) -> Passage | None:
    if not isinstance(quote, str) or not quote.strip():
        return None
    i = text.find(quote)
    return Passage(quote, i, i + len(quote)) if i >= 0 else None


def _passages(text: str, raw: object) -> tuple[Passage, ...]:
    out = []
    for q in raw if isinstance(raw, list) else []:
        p = _locate(text, q)
        if p:
            out.append(p)
    return tuple(out)


def _s(x: object) -> str:
    return x.strip() if isinstance(x, str) else ""


def analyze(
    article_text: str, *, article_url: str, text_scope: str, target: Target, bill_name: str, bill_summary: str,
    client, method_version: str,
) -> Analysis:
    prompt = build_prompt(article_text, text_scope, bill_name, bill_summary, target.provision_ref)
    raw: dict | None = None
    for _ in range(MAX_ATTEMPTS):
        try:
            text = client.generate(prompt, json_mode=True)
        except Exception as exc:  # noqa: BLE001 -- connection, timeout, HTTP status
            raise AnalysisError(f"model call failed: {exc}") from exc
        try:
            got = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(got, dict):
            raw = got
            break
    if raw is None:
        raise AnalysisError("model did not return a JSON object")

    headline = text_scope == "headline_only"
    # Tone
    tone = None
    t = raw.get("tone")
    if isinstance(t, dict):
        label = _s(t.get("label"))
        passages = _passages(article_text, t.get("passages"))
        if label not in TONES:
            label = "insufficient_evidence"
        if label != "insufficient_evidence" and not passages and not headline:
            label = "insufficient_evidence"
        tone = Tone(label, passages if label != "insufficient_evidence" else (), _s(t.get("rationale")))

    # Stances
    stances: list[Stance] = []
    seen: set[tuple[str, str | None]] = set()
    for s in raw.get("stances") if isinstance(raw.get("stances"), list) else []:
        if not isinstance(s, dict):
            continue
        role = _s(s.get("speaker_role"))
        if role not in ("narrator", "quoted_speaker"):
            continue
        name = _s(s.get("speaker_name")) or None
        if role == "narrator":
            name = None
        elif name is None:
            continue  # a quoted speaker without a name cannot be attributed
        if (role, name) in seen:
            continue
        seen.add((role, name))
        label = _s(s.get("label"))
        passages = _passages(article_text, s.get("passages"))
        rationale = _s(s.get("rationale"))
        if label not in STANCES or not passages or not rationale:
            label = "insufficient_evidence"
        if headline and label not in ("descriptive", "insufficient_evidence"):
            label = "descriptive" if passages else "insufficient_evidence"
        if label == "insufficient_evidence":
            stances.append(Stance(role, name, label))
        else:
            stances.append(Stance(role, name, label, passages, rationale))

    # Arguments
    arguments: list[Argument] = []
    if not headline:
        for a in raw.get("arguments") if isinstance(raw.get("arguments"), list) else []:
            if not isinstance(a, dict):
                continue
            role = _s(a.get("speaker_role"))
            name = _s(a.get("speaker_name")) or None
            passage = _locate(article_text, a.get("quote"))
            if role not in ("narrator", "quoted_speaker") or not _s(a.get("text")) or passage is None:
                continue
            if role == "quoted_speaker" and name is None:
                continue
            arguments.append(Argument(_s(a["text"]), passage, role, name if role == "quoted_speaker" else None))

    result = Analysis(
        article_url=article_url, article_text=article_text, text_scope=text_scope, target=target,
        method_version=method_version, tone=tone, stances=tuple(stances), arguments=tuple(arguments),
        rubric_version=RUBRIC_VERSION,
    )
    problems = validate(result)
    if problems:
        raise AnalysisError("analysis failed validation: " + "; ".join(problems[:5]))
    return result
