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

import logging

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Claim, ClaimSource, Entity, Source

logger = logging.getLogger(__name__)

MAX_BILL_TEXT_CHARS = 12_000  # keep prompts cheap; most bill summaries/digests fit well within this

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


def generate_bill_summaries(bill_number: str, title: str, bill_text: str, client: OllamaClient | None = None) -> dict[str, str]:
    """Run both prompts and return {'what_it_does': ..., 'who_it_affects': ...}.

    Pure function (no DB access) so it can be used standalone by the Step 2
    manual review script before any pipeline automation exists.
    """
    client = client or OllamaClient()
    truncated = bill_text[:MAX_BILL_TEXT_CHARS]

    what_it_does = client.generate(
        WHAT_IT_DOES_PROMPT.format(bill_number=bill_number, title=title, bill_text=truncated)
    )
    who_it_affects = client.generate(
        WHO_IT_AFFECTS_PROMPT.format(bill_number=bill_number, title=title, bill_text=truncated)
    )
    return {"what_it_does": what_it_does, "who_it_affects": who_it_affects}


def summarize_and_store(db: Session, entity: Entity, bill_text: str, primary_source: Source) -> list[Claim]:
    """Generate summaries for an already-ingested Bill entity and store them
    as Claims, each attached to the source the bill text came from.

    Only call this after Roadmap Step 2 (manual quality gate) has passed.
    """
    if entity.bill is None:
        raise ValueError("Entity is not a bill")

    client = OllamaClient()
    summaries = generate_bill_summaries(entity.bill.bill_number, entity.name, bill_text, client=client)

    claims = []
    for claim_type, text in summaries.items():
        claim = Claim(
            bill_entity_id=entity.id,
            claim_type=claim_type,
            claim_text=text,
            generated_by=f"llm:{client.model}",
        )
        db.add(claim)
        db.flush()
        db.add(ClaimSource(claim_id=claim.id, source_id=primary_source.id))
        claims.append(claim)

    db.commit()
    logger.info("Stored %d summary claims for bill %s", len(claims), entity.bill.bill_number)
    return claims
