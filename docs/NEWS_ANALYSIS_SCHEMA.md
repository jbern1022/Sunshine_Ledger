# News analysis: tone, stance and argument rubric, schema and benchmark protocol (v1 draft)

Todoist `6hrmjg4P4vHP9cGp` (parent `6hCMm72qhmhVGw2p`). Status: **draft for review, 2026-11-10.**
Code: `backend/app/news_analysis/schema.py` (record and validator), `benchmark.py` (scoring).
**No articles have been collected, no labels exist, and no model is called.** The schema work
was allowed to start independently of the access findings (`6hrmjg4JPMGpChGp`); which articles may
be stored and quoted depends on those findings, which are not done.

Owner scope (2026-10-29): both tone and target-specific stance, with extracted arguments and
supporting passages; narrator framing separated from quoted speakers; outputs are model estimates
with methodology, version and uncertainty, never facts about policy effects or public opinion; no
composite score for an official; no motive inference; public labels gated on measured error.

## What one record says

One analysis is about **one article and one bill target** (a bill, the text version it was judged
against, and optionally one provision). It contains:

| Part | Content |
|---|---|
| Article | URL, the text analyzed, and `text_scope`: `full_text`, `partial_text` or `headline_only` |
| Target | bill entity, bill text version, optional section reference |
| Tone | one label for the article's own wording, with a rationale and passages |
| Stances | zero or more: one per speaker (the narrator, and each quoted speaker by name) |
| Arguments | reasons given for or against, each with a speaker and one passage |
| Provenance | rubric version, method (model and prompt) version, `model_estimate: true` |
| Abstention | a reason, when the analysis declines to label anything |

There is **no numeric confidence**. Uncertainty is expressed as `insufficient_evidence`, as
abstention, as `partial_text` or `headline_only` scope, and (in evaluation) as measured error
rates with sample sizes. A percentage the system cannot justify is manufactured precision.

## Rubric

**Tone** describes the article's own wording about the matter, not what happens to anyone.

| Label | Use when |
|---|---|
| `negative` | the narrator's word choice is predominantly critical, alarming or disparaging about the bill or its effects |
| `positive` | predominantly favorable, praising or reassuring |
| `neutral` | reports facts or process in plain wording |
| `mixed` | both kinds of wording are substantial |
| `insufficient_evidence` | the text is too short, off-topic or unclear to say |

**Stance** is a speaker's position toward the **target bill or provision**, not toward the topic in
general and not the tone of the story.

| Label | Use when |
|---|---|
| `supports` | the speaker says or clearly implies the target should pass or stand |
| `opposes` | the speaker says or clearly implies it should fail or be repealed |
| `mixed` | the speaker backs some provisions or conditions and opposes others |
| `descriptive` | the speaker describes the target without expressing a position |
| `insufficient_evidence` | the text does not allow a label, or the target is ambiguous |

Rules that settle the hard cases (these are the tricky-case categories the benchmark must cover):

1. **Negative reporting is not opposition.** A grim story about a problem the bill would fix can be
   `negative` in tone with a `supports` stance toward the bill, or with `descriptive`.
2. **Quotation is not endorsement.** A quoted speaker's stance belongs to the speaker. The narrator's
   stance is labeled only from the narrator's own words (word choice, framing, editorial statements).
   A quote's presence alone never yields a narrator stance.
3. **One stance per speaker per target.** Different positions on different provisions are `mixed`, or
   separate records per provision.
4. **Negation and conditions count.** "Would not harm tenants" is not opposition; "supports it only if
   amended" is `mixed` or `descriptive` according to the passage, never plain `supports`.
5. **Ambiguous target means `insufficient_evidence`**: if the article could be about a different bill
   or an earlier version, abstain instead of guessing.
6. **A headline alone** may carry a tone and `descriptive` or `insufficient_evidence` stances. It
   cannot support `supports`, `opposes` or `mixed`, and cannot yield arguments. It is labeled so.
7. **Arguments** are reasons, as the speaker gave them, with the passage; the system does not add
   reasons the text does not state, and does not judge whether they are true.

## What the validator enforces

A label other than `insufficient_evidence` needs a rationale and at least one passage, and every passage
must be the article's exact text at the stated offsets (the same verbatim rule as promises and the
Who-it-affects layer). Quoted speakers need a name; the narrator has none. Tone and stance are
independent records. Headline-only limits above. `model_estimate` must be true. See
`tests/test_news_schema.py`.

## Benchmark protocol (to freeze before any held-out evaluation)

1. **Sample.** Lawfully accessible articles only (depends on the access findings), covering a range
   of outlets and perspectives, bills (state, local, federal delegation), and the six tricky categories
   (negative reporting backing a remedy, quote versus narrator, mixed provisions, negation, neutral
   description, ambiguous target), plus headline-only and partial-text cases.
2. **Two splits, fixed up front:** a development set for prompt and rubric work and a held-out set
   that is **not read by anyone building the system** and is used once per frozen method version.
3. **Reviewers.** At least two independent people per item, labeling tone, stance per speaker, and
   whether each passage supports its label. Disagreements are recorded, not averaged away; an
   adjudicated label is stored beside both originals.
4. **Agreement.** Cohen's kappa per dimension (`benchmark.cohens_kappa`). Low agreement is a rubric
   finding, not a system failure; the rubric is revised and the set relabeled before scoring.
5. **Reporting** (`benchmark.score`): tone and stance separately; per label precision and recall with
   support; **coverage** (share answered) reported next to accuracy on answered items so abstaining
   cannot hide errors; narrator versus quoted-speaker results separately; headline-only versus
   full-text separately; quote accuracy and attribution audited apart from stance accuracy; every
   figure with its sample size and an interval.
6. **Thresholds.** Acceptance thresholds for coverage and for per-label precision are written down
   and signed off **before** the held-out run. They are not invented here: a number chosen without
   data would be arbitrary. A failed gate is recorded with its remediation; thresholds are never
   weakened afterwards.
7. **Out of scope:** composite scores for officials or outlets, motive inference, claims about public
   opinion or policy effects, and any public display before the gates and the legal review pass.

## Open items

* Who the reviewers are, how they are recruited and paid, and how many items the sample needs (set
  by the intervals the thresholds require; decide after a pilot of about 30 items).
* Which text may be stored or quoted, from the access findings.
* The tone rubric's reviewers' notes: whether `mixed` tone needs a stricter definition after the pilot.
* Whether stance is also recorded toward the bill's sponsor. Not in v1: it risks motive inference.

## Runner (built 2026-11-10, internal only)

`app/news_analysis/analyze.py` turns one article and one bill target into a validated record using the same
`generate(prompt, json_mode=True)` client interface as the Impact Lens mapper. The model is not trusted for
anything checkable: it quotes passages, and the code finds each quote in the article itself and sets the offsets.
A quote that is not in the text verbatim is dropped, never repaired. A stance or tone left with no supporting
passage becomes `insufficient_evidence`; an argument with no real quote is dropped; a headline-only article is
capped at `descriptive`; a quoted speaker without a name is not kept. If the final record cannot pass
`schema.validate` the runner raises and nothing is produced. It fetches nothing, stores nothing, and has no
schedule: the data route (access findings) and the frozen benchmark come first. Tested with a fake model only;
**no real model output has been evaluated**.
