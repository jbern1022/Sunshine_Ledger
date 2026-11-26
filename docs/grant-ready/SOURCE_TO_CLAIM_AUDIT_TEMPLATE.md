# Source-to-claim audit: method and template

Grant-ready roadmap W2 (`6j2GRvh5mRQ29rqp`), Gate 2 condition (d): "a repeatable source-to-claim audit
template exists". Used for the accuracy sample (`6hxjxVHcfVhXFqvp`) and the W3 error ledger (Gate 3).

The question each audit answers: **can a reader trace every sentence the site generated back to the official
record, and does the record say what the sentence says?**

## 1. Sampling

* **Frame:** records with at least one generated claim (`what_it_does`, a layer block, a Who-it-affects entry).
* **Strata:** state bills; local legislation (ordinances, resolutions); local non-legislation items. Sample
  each stratum separately; never report one pooled number.
* **Draw:** random by `entity_id`, fixed seed recorded in the audit header, so a second auditor can redraw the
  same sample. Featured demo cases are audited **in addition to** the random draw, never as part of it.
* **Size:** 20 records per stratum for a first pass. With 20, an observed error rate of 0 still leaves an upper
  95% bound of about 14%; say so when reporting.
* **Snapshot:** record the claim text and `generated_by` / `input_hash` at audit time. Claims regenerate
  nightly; the audit is of what readers saw on the audit date.

## 2. Unit of audit

One **claim sentence**. A layer block or summary is split into sentences; each sentence is checked against the
source passage it relies on.

## 3. Checks per sentence

| Check | Question | Fail if |
|---|---|---|
| C1 Support | Does the cited or underlying source contain this statement? | No passage supports it |
| C2 Fidelity | Is the meaning preserved (actors, amounts, dates, conditions, modality)? | Changed number/date, dropped condition, "may" → "must", wrong actor |
| C3 Scope | Is the statement no broader or narrower than the source? | Generalises ("cities" for one city), or drops a limit ("for completed projects") |
| C4 Instrument | Is the record named correctly (bill, ordinance, resolution, motion, minutes)? | "This bill" for an ordinance or agenda item |
| C5 Quote | For quoted text: is it verbatim and locatable? | Not found verbatim (after whitespace/hyphen normalisation) |
| C6 Attribution | Is any person or body credited only with a documented role? | Sponsor/credit not in the record |
| C7 Uncertainty | Where the source is silent or ambiguous, does the claim say so instead of guessing? | Invented effect, cause or beneficiary |

## 4. Severity

| Severity | Meaning | Rule |
|---|---|---|
| **Critical** | A reader would act on something false: wrong legal effect, wrong amount/date, misattribution, fabricated quote | Withhold the claim from any demo; fix before Gate 3 |
| **Major** | Materially misleading scope or modality, but the underlying fact is right | Fix before the claim is featured; count in published rate |
| **Minor** | Wording or naming error with no change to meaning (C4 alone) | Count separately; batch fixes |

Report **critical + major** as the headline error rate per stratum, minor separately.

## 5. Record format (one row per sentence)

| Field | Example |
|---|---|
| audit_id, date, auditor, seed | `A-2026-11-25-01`, 2026-11-25, Claude (draft), seed 20261125 |
| entity_id, record number, stratum | `b6cb1f56-…`, Jacksonville 2026-0851-E, local legislation |
| claim_type, generated_by | `what_it_does`, `llm:…` |
| sentence | "This change allows cities to use these funds over a longer period." |
| source passage | "Ordinance 2023-335-E … is hereby amended to extend the deadline to fully expend funds for completed projects to no later than March 31, 2027." |
| checks failed | C3 (scope: "cities" for Jacksonville's own appropriation; drops "for completed projects") |
| severity | Major |
| disposition | Correction filed / prompt issue / withheld / accepted |

## 6. Worked example: Jacksonville Ordinance 2026-0851-E (`what_it_does`)

| Sentence | Checks | Severity |
|---|---|---|
| "This bill extends the deadline for spending funds allocated for a housing program." | C4 fails ("bill" for an ordinance). Otherwise supported. | Minor |
| "The original deadline was June 30, 2026, but it has been extended to March 31, 2027." | Pass. Note the extension was approved by the Florida Housing Finance Corporation; the ordinance aligns the city's appropriation with it. | — |
| "This change allows cities to use these funds over a longer period." | C3 fails: one city's appropriation, and only for completed projects. | Major |
| "The mayor and corporation secretary are authorized to sign documents to make this extension official." | Pass (Section 3). | — |

Result for this record: 4 sentences, 1 major, 1 minor.

## 7. Reporting

Per stratum: records audited, sentences audited, critical, major, minor, rate with its 95% upper bound, top
failure checks, and examples. Publish limitations with the number (sample size, single auditor unless a second
auditor re-checks a subset, audit date). An independent second auditor on at least 25% of sentences is the
target before any public accuracy claim (`6hxjxVHcfVhXFqvp`).
