"""Plain-language summarization via Ollama (BRD 5.2).

Generates two claims per bill: "what it does" and "who it affects". Both
prompts push the model toward plain language and explicitly forbid
speculation beyond the bill text, since summaries are shown to the public
before any editorial review layer exists (BRD 5.5: flags route to manual
review, not open editing).

Runs against local Ollama (home-lab Powerstation) rather than a hosted API,
per the BRD's cost-aware requirement at nationwide scale (150,000+
bills/year). Bill text is truncated to keep prompts small and cheap.
"""

from __future__ import annotations

import hashlib
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Claim, ClaimSource, Entity, Source

logger = logging.getLogger(__name__)

MAX_BILL_TEXT_CHARS = 12_000  # keep prompts cheap; most bill summaries/digests fit well within this

# Bump when a prompt changes in a way that should invalidate stored
# summaries. It's part of the input hash, so bumping it makes the batch job
# re-summarize everything on its next run -- which is the intended effect,
# but it is not free at scale. Don't bump for typo fixes.
PROMPT_VERSION = "1"

# Summary fields a cheaper model may write when one is configured.
# "who_it_affects" is deliberately absent: on a 3B model it fell back to
# "does not specify a particular affected group" twice as often as on the
# 8B, and that field is precisely what justified moving to full bill text
# in the first place. See docs/LLM_MODEL_ROUTING.md.
FAST_MODEL_CLAIM_TYPES = frozenset({"what_it_does"})


def model_for_claim_type(claim_type: str, *, quality_model: str, fast_model: str = "") -> str:
    """Which model generates a given summary field.

    Measured on real bills, the two prompts are not equally sensitive to
    model size (see docs/LLM_MODEL_ROUTING.md): "what it does" came out
    comparable on a 3B and an 8B, while "who it affects" doubled its
    non-answer rate on the 3B -- and that field is the one the whole
    full-text switch was justified on. So routing is per-field, not
    per-bill: a cheaper model may write "what it does" while "who it
    affects" stays on the quality model.

    With no fast model configured (the default), everything uses the
    quality model.
    """
    if fast_model and claim_type in FAST_MODEL_CLAIM_TYPES:
        return fast_model
    return quality_model


def summary_input_hash(
    bill_text: str, *, model: str, fast_model: str = "", prompt_version: str = PROMPT_VERSION
) -> str:
    """Fingerprint everything that determines the generated summaries.

    Covers the models and prompt version, not just the text: a summary
    produced by a different model or an older prompt is stale even when the
    bill itself hasn't changed. Hashes the *truncated* text, since that's
    what is actually sent to the model.

    `fast_model` is part of the fingerprint because it changes the output of
    whichever fields it handles. Turning routing on or off, or swapping the
    cheap model, therefore invalidates stored summaries and re-generates
    them -- which is the intended behaviour, and not free at corpus scale.

    It is only appended when set, so that adding this parameter did not by
    itself change the fingerprint of every already-stored claim and trigger
    a full re-summarization producing the same summaries again.
    """
    parts = [prompt_version, model]
    if fast_model:
        parts.append(f"fast={fast_model}")
    parts.append(bill_text[:MAX_BILL_TEXT_CHARS])
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()

WHAT_IT_DOES_PROMPT = """You are summarizing a piece of legislation for a general public audience with no legal background.

Bill: {bill_number} — {title}

Bill text or official summary:
\"\"\"
{bill_text}
\"\"\"

Write a 2-4 sentence plain-language summary of what this bill actually does. Rules:
- Use everyday words, not legal jargon. If you must use a legal term, explain it in the same sentence.
- Only state what is in the text above. Do not speculate about intent, politics, or effects not stated in the text.
- Do not use adjectives that imply a value judgment (e.g. "harmful", "beneficial", "important").
- Output only the summary text, no preamble.
"""

WHO_IT_AFFECTS_PROMPT = """You are identifying who is affected by a piece of legislation, for a general public audience.

Your default assumption should be that the text DOES name or imply a specific affected group -- most bills regulate, fund, penalize, license, or benefit some named category of people, profession, or institution, even briefly. Read closely for nouns like officers, teachers, contractors, spouses and children of X, licensees, counties, students, employees, tenants, etc. -- these all count as a specific group, even if the phrase is short.

Only use the fallback below if the text is truly generic (e.g. naming a state symbol, renaming a road, a purely ceremonial/procedural act with no named beneficiary or regulated party at all).

Examples:

Text: "Designates the tulip as the official state flower."
Answer: The available text does not specify a particular affected group beyond the general public.

Text: "Requires licensed roofing contractors to complete 4 hours of hurricane-mitigation training annually."
Answer: Licensed roofing contractors in Florida, who must now complete annual hurricane-mitigation training.

Text: "Increases penalties for battery committed against law enforcement officers."
Answer: Law enforcement officers, who gain stronger legal protection, and anyone charged with battery against them, who now faces increased penalties.

Text: "Sets aside tuition assistance funds for spouses and children of active members of the Florida National Guard."
Answer: Spouses and children of active Florida National Guard members, who become eligible for tuition assistance.

Now identify who this bill affects, in 1-2 plain sentences using only what the text below supports. Do not add agencies, institutions, or industries the text doesn't mention just because they sound plausible for this topic. Write plain prose -- no bullet points, no lists, no headers. If the text truly has no named affected group per the rule above, respond with exactly: "The available text does not specify a particular affected group beyond the general public."

Bill: {bill_number} — {title}

Bill text or official summary:
\"\"\"
{bill_text}
\"\"\"

Answer:"""


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, host: str | None = None, model: str | None = None) -> None:
        self.host = (host or settings.ollama_host).rstrip("/")
        self.model = model or settings.ollama_model
        self._client = httpx.Client(timeout=120.0)

    def generate(self, prompt: str) -> str:
        resp = self._client.post(
            f"{self.host}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        data = resp.json()
        if "response" not in data:
            raise OllamaError(f"Unexpected Ollama response: {data}")
        return data["response"].strip()


def generate_bill_summaries(
    bill_number: str,
    title: str,
    bill_text: str,
    client: OllamaClient | None = None,
    *,
    fast_client: OllamaClient | None = None,
) -> dict[str, str]:
    """Run both prompts and return {'what_it_does': ..., 'who_it_affects': ...}.

    `fast_client`, when given, handles the fields listed in
    FAST_MODEL_CLAIM_TYPES; everything else uses `client`. Passing an
    explicit `client` and no `fast_client` keeps this single-model, which is
    what the Step 2 review script and the model comparisons rely on.

    Pure function (no DB access) so it can be used standalone by the Step 2
    manual review script before any pipeline automation exists.
    """
    client = client or OllamaClient()
    truncated = bill_text[:MAX_BILL_TEXT_CHARS]

    prompts = {
        "what_it_does": WHAT_IT_DOES_PROMPT,
        "who_it_affects": WHO_IT_AFFECTS_PROMPT,
    }
    out: dict[str, str] = {}
    for claim_type, prompt in prompts.items():
        chosen = fast_client if (fast_client and claim_type in FAST_MODEL_CLAIM_TYPES) else client
        out[claim_type] = chosen.generate(
            prompt.format(bill_number=bill_number, title=title, bill_text=truncated)
        )
    return out


def summarize_and_store(db: Session, entity: Entity, bill_text: str, primary_source: Source) -> list[Claim]:
    """Generate summaries for an already-ingested Bill entity and store them
    as Claims, each attached to the source the bill text came from.

    Only call this after Roadmap Step 2 (manual quality gate) has passed.
    """
    if entity.bill is None:
        raise ValueError("Entity is not a bill")

    client = OllamaClient()
    fast_model = settings.ollama_model_fast
    fast_client = OllamaClient(model=fast_model) if fast_model else None

    summaries = generate_bill_summaries(
        entity.bill.bill_number, entity.name, bill_text, client=client, fast_client=fast_client
    )
    input_hash = summary_input_hash(bill_text, model=client.model, fast_model=fast_model)

    claims = []
    for claim_type, text in summaries.items():
        # Attribute each claim to the model that actually wrote it -- with
        # routing on, the two fields can come from different models, and
        # "which model said this" matters when reviewing a flagged claim.
        generated_by = "llm:" + model_for_claim_type(
            claim_type, quality_model=client.model, fast_model=fast_model
        )

        # Update the existing claim in place rather than replacing it.
        # Flags reference claims with ON DELETE CASCADE, so deleting and
        # re-inserting on every refresh would silently destroy the user
        # reports (BRD 5.5) attached to the old claim.
        existing = db.execute(
            select(Claim).where(
                Claim.bill_entity_id == entity.id,
                Claim.claim_type == claim_type,
                Claim.generated_by.like("llm:%"),
            )
        ).scalars().first()

        if existing is not None:
            existing.claim_text = text
            existing.generated_by = generated_by
            existing.input_hash = input_hash
            claim = existing
        else:
            claim = Claim(
                bill_entity_id=entity.id,
                claim_type=claim_type,
                claim_text=text,
                generated_by=generated_by,
                input_hash=input_hash,
            )
            db.add(claim)
        db.flush()

        already_linked = db.execute(
            select(ClaimSource).where(
                ClaimSource.claim_id == claim.id, ClaimSource.source_id == primary_source.id
            )
        ).scalars().first()
        if already_linked is None:
            db.add(ClaimSource(claim_id=claim.id, source_id=primary_source.id))
        claims.append(claim)

    db.commit()
    logger.info("Stored %d summary claims for bill %s", len(claims), entity.bill.bill_number)
    return claims
