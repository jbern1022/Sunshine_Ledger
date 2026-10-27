# Evidence model: gap map and minimum vertical slice

Status: draft for Joe's review, 2026-10-26 (static review of `main` c80ef68; no
production data was read). Todoist `6hr2PW7GfrmX82fG`; it is the dependency for
milestone step 2 (`6hr2RCR6xGgCW42G`) and shares its cases with `6hg8Xmf8fjvWRXmG`.
Spec: Notion "Accountability Case & Evidence Graph Data Model v1" (partial v1; its own
Status section says Expected Effect/Observed Outcome detail, Scope and correction/review
integration are still undefined).

The spec's own rule governs this document: *design a small kernel, prove it against real
cases, extend only when evidence demands it.* So this maps what exists, marks what the
three validation cases would force, and stops there.

## What exists today

| Table | Shape | Notes |
|---|---|---|
| `sources` | url, document_reference, publisher, source_type, retrieved_at, metadata_json | Provenance for ingested facts. The closest thing to a Record, but it holds no excerpt, record type, subject or event date. |
| `claims`, `claim_sources` | one flat generated statement per bill (`what_it_does`, `who_it_affects`, ...) | Bill-centered; no version, no evidence relationship type, no evidence state. Still used by summaries, `rhetoric_gap`, people and flag code. |
| `bill_layers` (+ `_sources`, `_reviews`) | append-only versions per (bill, layer, origin); `evidence_state` supported / insufficient_evidence; `superseded_at`; method_version; input_hash | The real implementation of versioning and evidence state, for generated bill blocks only. |
| `bill_layer_criteria` (+ reviews) | structured Impact Lens criteria per Who entry | Review state is separate from content. |
| `events` | entity-bound typed occurrence, date, title, attributes JSONB, one `source_id` | Holds actions, votes, amendments. One entity and one source per event. |
| `relationships` | entity to entity, type, attributes, one `source_id` | Sponsor, co-sponsor and similar structural links; no validity period. |
| `flags` | challenge to a bill object, with triage, severity, disputed_since | The Challenge object. |
| `correction_records` | prior/current text and version, severity, trigger, evidence_links JSONB, origin | The Correction object; append-only. |
| `responses` | verified right of reply, supersedable | |
| `bill_text_versions`, `staff_analyses` | versioned documents | Records for lineage comparisons. |

## Concept by concept

| Spec concept | Status | Gap | Reuse |
|---|---|---|---|
| Source | Present | none for now | `sources` |
| Record (what a source documents, with excerpt, type, subject, date) | Partial | no excerpt, record type, subject entity, event date | extend `sources` or `metadata_json` first; a `records` table only if three cases need it |
| Claim Identity | Missing for non-generated claims | the proposition tracked across its life | new |
| Claim Version | Present only for bill layers | accountability claims have none | pattern from `bill_layers` (append-only, `superseded_at`) |
| ClaimEvidence relationship (supports / challenges / contradicts / qualifies / corroborates, with scope and limitations) | Missing | `claim_sources` is an unlabelled many-to-many | new table; `correction_records.evidence_links` already uses supporting/challenging/contradicting roles in JSONB, which shows the need |
| Evidence State and its history | Partial | two states for bill layers, no history table; the spec's states and "Cannot determine" are not modelled | extend the enum per case; history can be the version rows |
| Claim type vs evidence state vs review state kept separate | Partial | layers keep evidence_state apart from review; claims do not | copy the layer pattern |
| Provenance chain / transformation provenance | Partial | `input_hash`, `method_version`, `generated_by` exist for layers; no derived-from link between records, so shared origin cannot be shown | new `derived_from` link only when a case needs independence shown |
| Event (typed, participants, institutional capacity, many records) | Partial | one entity and one source per event; no participants or capacity; statements are not first-class | `events` + `attributes` for now (see slice) |
| Statement Event with attribution form | Missing | speaker, form (recording, transcript, quote, paraphrase, anonymous), context | `events.event_type = 'statement_made'` plus attributes |
| Time-bounded relationships (office held during a period) | Missing | `relationships` has no validity period | add `valid_from`, `valid_to` when a case needs a role at a date |
| Accountability Case (bounded question, versioned, references not copies) | Missing | | new, fixtures first |
| Case Assessment (versioned, separate findings, no composite score) | Missing | | new with the case |
| Interpretation / Material Assumption | Present for bills | | bill layers |
| Expected Effect / Observed Outcome | Expected Effect present; Observed Outcome missing and the spec says undefined | the spec itself lists this as open | defer |
| Scope / Affected Population | Present (Who it affects, Impact Lens) | | reuse |
| Challenge, Correction, Right of reply | Present for bill objects | `object_type` check allows bill, claim, bill_layer, amendment, vote, page_copy; a case, claim version or assessment is not a target | extend the allowed set |
| Entity resolution and attribution | Missing as a process | no identity-review states, no merge/split audit record | not needed for the first three cases unless a person is matched across sources |
| Methodology version | Present as strings | no registry | keep strings |

## What the three validation cases force

1. **Fulfilled commitment.** Needs a dated statement (Statement Event), the commitment
   proposition as a versioned claim, a later action (bill, vote, signature: existing
   events), and a classification (fulfilled / partial) with the evidence for each link.
   Forces: statement events, claim identity and versions, evidence relationships,
   an evidence state beyond "supported".
2. **Failed enactment with a documented disposition.** Needs the bill's history and the
   recorded failure reason. Most of this already exists (`events`, action history). Forces
   very little new except tying the disposition to a claim about why it failed (a stated
   reason versus an inferred one stay separate).
3. **Claimed credit versus documented role.** Needs the credit statement, the documented
   sponsorship or vote role at that date, and counterevidence. Forces: time-bounded
   roles, supporting and challenging evidence on the same claim, the "Cannot determine"
   state, and the correction/reply objects pointing at a claim version. This case is the
   one that tests the evidence relationship model.

## Minimum vertical slice

Order matters; each step is useful and none presumes the next.

0. **Fixtures and the display.** One case as a typed fixture (like
   `frontend/lib/__fixtures__/hb1389.json`): statement, role, action, outcome,
   counterevidence, assessment, reply, version history. Build the case page against it,
   labelled as a prototype. This settles what a reader needs before any schema is
   committed, and it is what the milestone allows.
1. **Statement events.** Use `events` with `event_type = 'statement_made'`, attributes for
   speaker, attribution form, venue, quote and capacity; the document is a `sources` row.
   No migration beyond maybe an index.
2. **Claim identity, versions and evidence.** New tables, named by the spec:
   `acct_claims` (identity), `acct_claim_versions` (append-only, `superseded_at`, as bill
   layers), `acct_claim_evidence` (version, source or event, relationship type, scope,
   limitations), and an evidence-state column on the version. A separate name from the
   existing `claims` avoids disturbing summaries and flags.
3. **Case and assessment.** `acct_cases` (question, scope, methodology version) and
   `acct_case_assessments` (versioned findings, one row per finding, no composite).
4. **Targets for challenge, correction and reply.** Extend `flags.object_type` and
   `correction_records.object_type` to the new objects.
5. **Time-bounded roles**, only if case 3 needs them: `valid_from` / `valid_to` on
   `relationships`.

Not in the slice: a universal Record table, independence analysis, entity-resolution
review states, Observed Outcome comparison, nationwide or other-vertical objects.

## Implementation dependencies versus already-accepted methodology

- *Accepted, needs only code:* claim/record split, versioning rules, relationship types,
  no composite score, statement-as-event, separate type/evidence/review states.
- *Needs a decision before code:* the evidence-state vocabulary (the spec names
  "Cannot determine"; which others?), how a credit claim is stored (a claim about a
  statement, or a statement event plus a claim about its accuracy), and whether the case
  assessment's findings are rows or JSON.
- *Blocked on others:* attribution and applicable reviewer/legal gates for publishing
  (milestone step 2), and the validation cases themselves (`6hg8Xmf8fjvWRXmG`).

## Risks

- Building step 2 before step 0 would freeze a schema on one unvalidated example.
- The existing `claims` table carries the generic name, so an unqualified "claim" in
  tickets is ambiguous; this document uses `acct_` only as a working prefix.
- `events` has one entity per event; a vote involving a person, a bill and a body needs
  the participant list, or one event per participant. Decide with case 1.
