"""Roadmap Step 2 (GATE): manually validate summarization quality.

Runs the plain-language prompts against a batch of bills and writes the
output to a markdown file for a human to read and judge critically —
deliberately *before* any pipeline automation is built on top of the LLM
step (see Roadmap Section 8, Step 2, and Charter Section 9 Key Risks).

This script does not touch the database. It is meant to be run standalone
against a batch of 15-20 *real* Florida bills (pulled via
`legiscan.LegiScanClient` once you have an API key) before Step 4
(automated pipeline) is trusted.

Usage:
    python -m app.pipeline.review_summaries [--input path/to/bills.json] [--output review.md]

Input JSON shape: a list of {"bill_number": str, "title": str, "bill_text": str}.
Defaults to the bundled sample bills, which are illustrative placeholders,
NOT the real 15-20 bill sample the gate requires.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.pipeline.summarize import OllamaClient, generate_bill_summaries

DEFAULT_INPUT = Path(__file__).parent / "sample_data" / "sample_bills_for_review.json"
DEFAULT_OUTPUT = Path(__file__).parent / "sample_data" / "review_output.md"


def run(input_path: Path, output_path: Path) -> None:
    bills = json.loads(input_path.read_text())
    client = OllamaClient()

    lines = [
        "# Sunshine Ledger — Summarization Quality Review",
        "",
        f"Model: `{client.model}` via `{client.host}`",
        f"Bills reviewed: {len(bills)}",
        "",
        "**Reviewer instructions:** for each bill below, check the summary against the source text.",
        "Flag hallucinated facts, missed material provisions, and any implied value judgment.",
        "Per the Roadmap's build-order gate, do not proceed to Step 4 (pipeline automation)",
        "until this batch (15-20 real bills) reads as accurate and legible.",
        "",
        "---",
        "",
    ]

    for bill in bills:
        print(f"Summarizing {bill['bill_number']}...")
        summaries = generate_bill_summaries(bill["bill_number"], bill["title"], bill["bill_text"], client=client)

        lines += [
            f"## {bill['bill_number']} — {bill['title']}",
            "",
            "**Source text (truncated):**",
            f"> {bill['bill_text'][:500]}{'...' if len(bill['bill_text']) > 500 else ''}",
            "",
            "**What it does:**",
            summaries["what_it_does"],
            "",
            "**Who it affects:**",
            summaries["who_it_affects"],
            "",
            "**Reviewer verdict:** ☐ Accurate  ☐ Needs prompt changes  ☐ Reject",
            "",
            "---",
            "",
        ]

    output_path.write_text("\n".join(lines))
    print(f"\nWrote review output to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.input, args.output)
