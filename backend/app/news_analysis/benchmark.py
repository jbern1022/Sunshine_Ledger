"""Scoring for the human-reviewed news-analysis benchmark (docs/NEWS_ANALYSIS_SCHEMA.md).

Pure functions over labels. No benchmark data exists yet and none is invented here: a
reviewer-labeled set is a deliverable for people. What this fixes in advance is HOW results are
reported, so thresholds cannot be chosen after seeing them: stance and tone are scored
separately, abstentions are reported as coverage rather than hidden, and every figure comes with
its sample size.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class LabelReport:
    n: int
    answered: int  # items the system labeled (did not abstain)
    coverage: float  # answered / n
    accuracy_on_answered: float | None
    per_label: dict[str, dict[str, float | int | None]]  # precision, recall, support


def cohens_kappa(a: list[str], b: list[str]) -> float | None:
    """Agreement between two reviewers beyond chance; None when it is undefined."""
    if len(a) != len(b) or not a:
        raise ValueError("two equal, non-empty label lists are required")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def score(gold: list[str], predicted: list[str | None], *, abstain_label: str = "insufficient_evidence") -> LabelReport:
    """`predicted` None or `abstain_label` counts as an abstention. Accuracy is over answered items
    only, so abstaining is visible as lower coverage, never as a free pass or a silent error."""
    if len(gold) != len(predicted) or not gold:
        raise ValueError("gold and predicted must be equal, non-empty lists")
    n = len(gold)
    pairs = [(g, p) for g, p in zip(gold, predicted) if p is not None and p != abstain_label]
    answered = len(pairs)
    per_label: dict[str, dict[str, float | int | None]] = {}
    for label in sorted({g for g in gold} | {p for _, p in pairs}):
        tp = sum(1 for g, p in pairs if g == label and p == label)
        pred_n = sum(1 for _, p in pairs if p == label)
        gold_n = sum(1 for g in gold if g == label)
        per_label[label] = {
            "precision": tp / pred_n if pred_n else None,
            "recall": tp / gold_n if gold_n else None,  # over all gold items, abstentions included
            "support": gold_n,
        }
    return LabelReport(
        n=n, answered=answered, coverage=answered / n,
        accuracy_on_answered=(sum(g == p for g, p in pairs) / answered) if answered else None,
        per_label=per_label,
    )
