"""Independent grader pilot (Sunshine $100 gate; Todoist 6hxjxV7MMf42RJ2p).

A different model family (Claude on Amazon Bedrock) checks the local model's layer
statements against the bill text, using the checks in
docs/grant-ready/SOURCE_TO_CLAIM_AUDIT_TEMPLATE.md (C1-C7, critical/major/minor).
Sampling only: it never writes to the site. Every "fail" must quote the passage it
relies on, and that quote is then checked mechanically against the bill text, so a
grader that invents evidence is caught.

    python3 grade_layers.py SAMPLE.jsonl OUT.jsonl   (AWS profile with bedrock:InvokeModel)
"""

from __future__ import annotations

import json
import re
import sys

MODEL = "us.anthropic.claude-sonnet-4-6"  # US-only cross-region profile (data stays in the US)

RUBRIC = """You are an independent auditor for a civic website that explains Florida legislation. Another model wrote
the statements below about one legislative record. Check each statement ONLY against the record's text.

Checks (fail a statement if any applies):
C1 Support: no passage of the text supports it.
C2 Fidelity: changed actor, amount, date, condition, or modality ("may" became "must", or the reverse).
C3 Scope: broader or narrower than the text (e.g. "cities" for one city; a dropped limit).
C4 Instrument: names the record wrongly ("this bill" for an ordinance, resolution or agenda item).
C5 Quote: a field marked QUOTE is not verbatim in the text.
C6 Attribution: credits a person or body with something the text does not say they do.
C7 Uncertainty: invents an effect, cause or beneficiary the text does not state (statements in EXPECTED EFFECT
   may describe consequences, but only ones that follow directly from a mechanism in the text and are worded
   conditionally).

Severity for a failed statement: critical = a reader would act on something false (wrong legal effect, amount,
date, actor, fabricated quote); major = materially misleading scope or modality but the underlying fact is
right; minor = naming/wording only (C4 alone).

Return JSON only, no prose: {"results":[{"n":1,"verdict":"pass"|"fail","checks":["C3"],"severity":"none"|"minor"|
"major"|"critical","reason":"at most 30 words","evidence":"exact passage copied from the text that shows the
problem, or null for pass"}]}. One result per statement, same n. Be strict but fair: wording differences that keep
the meaning are a pass."""


def statements(rec: dict) -> list[dict]:
    out = []
    for layer in ("interpretation", "expected_effect", "who_it_affects"):
        for it in (rec.get("layers") or {}).get(layer, {}).get("items") or []:
            text = it.get("text") or ""
            if layer == "who_it_affects":
                text = f"{it.get('group', '')}: {text}"
            out.append({"layer": layer, "text": text, "quote": it.get("quote")})
    return out


def prompt(rec: dict, stmts: list[dict]) -> str:
    lines = []
    for i, s in enumerate(stmts, 1):
        lines.append(f"{i}. [{s['layer'].upper().replace('_', ' ')}] {s['text']}"
                     + (f"\n   QUOTE: {s['quote']}" if s.get("quote") else ""))
    kind = "a Florida Legislature bill" if rec["level"] == "state" else f"a {rec['jurisdiction']} ({rec['level']}) record"
    return (f"{RUBRIC}\n\nRecord: {rec['bill_number']} ({kind}), {rec['name']}\n\nTEXT:\n\"\"\"\n{rec['text']}\n\"\"\"\n\n"
            "STATEMENTS:\n" + "\n".join(lines))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"-\s*\n\s*", "", s or "")).strip().lower()


def evidence_found(evidence: str | None, text: str) -> bool | None:
    if not evidence:
        return None
    return norm(evidence) in norm(text)


def parse(raw: str) -> list[dict]:
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0))["results"] if m else []


def main(sample: str, out: str) -> None:
    import boto3
    from botocore.config import Config

    br = boto3.client("bedrock-runtime", region_name="us-east-2",
                      config=Config(retries={"max_attempts": 5, "mode": "adaptive"}, read_timeout=300))
    tokens_in = tokens_out = 0
    with open(out, "w") as fh:
        for line in open(sample):
            if not line.startswith("{"):
                continue
            rec = json.loads(line)
            stmts = statements(rec)
            if not stmts:
                continue
            resp = br.converse(modelId=MODEL, messages=[{"role": "user", "content": [{"text": prompt(rec, stmts)}]}],
                               inferenceConfig={"maxTokens": 8000, "temperature": 0})
            tokens_in += resp["usage"]["inputTokens"]
            tokens_out += resp["usage"]["outputTokens"]
            results = {r["n"]: r for r in parse(resp["output"]["message"]["content"][0]["text"])}
            for i, s in enumerate(stmts, 1):
                r = results.get(i, {"verdict": "missing"})
                fh.write(json.dumps({"bill": rec["bill_number"], "level": rec["level"], "id": rec["id"], "n": i, **s,
                                     **r, "evidence_found": evidence_found(r.get("evidence"), rec["text"])}) + "\n")
            print(f"{rec['bill_number']:<12} {len(stmts):>3} statements, "
                  f"{sum(1 for r in results.values() if r.get('verdict') == 'fail')} fail", flush=True)
    print(json.dumps({"model": MODEL, "input_tokens": tokens_in, "output_tokens": tokens_out}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
