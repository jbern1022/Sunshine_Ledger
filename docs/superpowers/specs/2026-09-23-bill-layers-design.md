# Bill Says / Interpretation / Expected Effect — design

**Date:** 2026-09-23
**Todoist:** `6hX5mHjFXJQ4R3pp` (P2)
**Governing docs (Notion):** Bernal Labs Trust & Accountability Doctrine; Sunshine Ledger — Evidence & Source Hierarchy (Record, Interpretation, Expected Effect evidence; evidence state vs review state); Corrections & Historical Integrity.
**Related open tasks:** evidence taxonomy `6hWgXrhpwQ75fJQp`, append-only corrections `6hWgXrmHJPmhfhQp`. This spec implements the subset of both that this feature needs, using the doctrine's field names so those tasks can extend it.

## Goal

Every supported bill page separates three materially different kinds of claim, so a reader never has to guess which one they are reading:

1. **Bill Says** — the bill's own words (Record evidence).
2. **Interpretation** — what the change means (Interpretation evidence).
3. **Expected Effect** — what may happen (Expected Effect evidence; forecasts, not facts).

Each layer shows who produced each statement: the bill text, the Florida legislative staff analysis, or Sunshine Ledger's own AI analysis. Staff and Sunshine Ledger content are both shown, side by side, each clearly labeled.

## Decisions

| Question | Decision |
|---|---|
| Source of Interpretation / Expected Effect | Staff analysis where one exists, **and** a Sunshine Ledger AI analysis, shown as separate labeled blocks |
| Sunshine Ledger Expected Effect | Allowed only for effects created by a specific bill section, which must be cited and verified to exist; conditional wording enforced |
| Bill Says | 2–4 quotes, each verified verbatim against the stored full text; unverifiable quotes are dropped |
| Preserving past versions | Append-only rows; earlier versions visible on the page |
| Storage | New `bill_layers` table next to `claims`; `claims` is unchanged |

## Data coverage (production, 2026-09-23)

- 2,547 bills; 2,115 with full text.
- 890 bills with staff analyses (4,308 analyses). Of those analyses, ~45% contain "Effect of Proposed Changes" and ~70% contain "Fiscal Impact".
- Staff analyses exist only for Florida state bills (LegiScan). Miami (iQM2) and Jacksonville (Legistar) bills get Bill Says (where there is full text) and Sunshine Ledger blocks only.

## Data model

New table `bill_layers`, append-only:

| Column | Notes |
|---|---|
| `id`, `created_at` | existing mixins |
| `bill_entity_id` | FK `entities.id`, cascade delete |
| `layer` | `bill_says` \| `interpretation` \| `expected_effect` |
| `origin` | `bill_text` \| `legislative_staff` \| `sunshine_ledger_ai` |
| `version` | int, increments per (bill, layer, origin), starting at 1 |
| `superseded_at` | null = current |
| `evidence_state` | `supported` \| `insufficient_evidence` |
| `scope_note` | human-readable scope, e.g. "Staff analysis, Appropriations Committee, 2026-09-12" or "First 12,000 characters of bill text" |
| `items` | JSONB list of `{text, section_ref, quote, assumptions: [], affected_groups: []}`; unused fields null/empty |
| `generated_by` | e.g. `llm:llama3.1:8b` |
| `method_version` | per-layer prompt/method version string, e.g. `bill_says/1` |
| `input_hash` | sha256 of input text + model + method version |

Join table `bill_layer_sources (bill_layer_id, source_id)`, reusing `sources`.

Constraints:
- Partial unique index on `(bill_entity_id, layer, origin) WHERE superseded_at IS NULL` — at most one current row.
- Unique `(bill_entity_id, layer, origin, version)`.

Allowed (layer, origin) pairs: `bill_says/bill_text`; `interpretation/legislative_staff`; `interpretation/sunshine_ledger_ai`; `expected_effect/legislative_staff`; `expected_effect/sunshine_ledger_ai`. Enforced in code and by a CHECK constraint.

**"Not yet evaluated" is not stored.** It means no row exists. "No staff analysis published" also means no row exists and the bill has no `staff_analyses` rows. Absence of analysis is never written as a finding.

**Append-only rule:** the pipeline only inserts. When an input hash changes, it inserts version N+1 and sets `superseded_at` on version N in the same transaction. No code path updates `items`, `evidence_state`, or `scope_note` on an existing row.

## Human review

Every AI-produced block shows one of two review labels, so readers can tell whether a person has checked it:

- **AI-generated · not reviewed by a person**
- **AI-generated · reviewed by a person on <date>**

"AI-generated" stays in the reviewed label: review confirms the text, it doesn't change who wrote it.

Which blocks carry a review label:
- `sunshine_ledger_ai` blocks (Interpretation, Expected Effect).
- `legislative_staff` blocks too, because their statements are condensed from the staff analysis by AI. Badge: "Legislative staff analysis · <committee>, <date> · condensed by AI · <review label>".
- `bill_says` does not: its quotes are checked word for word by code. It shows "Quotes checked word for word against the bill text" instead.

**Storage (keeps rows append-only).** Review is recorded in its own append-only table, never as an update to `bill_layers`:

`bill_layer_reviews`: `id`, `bill_layer_id` (FK), `decision` (`approved` only in this spec), `reviewer` (admin username, internal only, never shown publicly), `note` (internal), `created_at`.

A version counts as reviewed when it has an `approved` review. The API derives `review_status` (`not_reviewed` / `reviewed`) and `reviewed_at` from this table.

**A new version starts unreviewed.** When the pipeline supersedes a reviewed version, the new current version shows "not reviewed" until a person reviews it. The earlier-versions list keeps the old version's "reviewed on <date>" label.

**How a person reviews.** Admin-only endpoints, same HTTP Basic auth as the flag review queue (`require_admin`):
- `GET /bill-layers/admin/unreviewed?limit=N`: current versions with no approval, oldest first, including the bill number, the items and the sources needed to check them.
- `POST /bill-layers/admin/{id}/review` with `{decision: "approved", note?}`. Rejected with 409 if the version is superseded (review the current one instead).

No rejection path in this spec: if a reviewer finds a problem, they file a flag, and the correction goes through the corrections spec (`6hWgXrmHJPmhfhQp`). A review UI is out of scope; the endpoints can be used with curl or a small admin page later.

## Pipeline

New modules:
- `app/pipeline/bill_layers.py` — pure functions: prompts, generation, verification, staff-section extraction. No DB writes, so they are testable and reusable by the review script.
- `app/pipeline/bill_layers_batch.py` — selection by input hash, writes rows, one bill's failure does not stop the batch. CLI: `python -m app.pipeline.bill_layers_batch [--limit N] [--dry-run]`.
- `app/pipeline/review_bill_layers.py` — quality gate: runs all layers for a chosen sample, writes a markdown report, never writes to the DB.

Runs nightly as a step in `scripts/run-ingestion.sh`, after summarization. Uses the quality model (`OLLAMA_MODEL`), not the fast model.

### Bill Says (origin `bill_text`)
- Input: `bill.full_text`, truncated at the existing `MAX_BILL_TEXT_CHARS`.
- Model returns JSON: 2–4 `{section_ref, quote}`.
- **Verification:** normalize whitespace on both sides; keep a quote only if it is an exact substring of the *truncated* text. Dropped quotes are logged with the bill number.
- ≥1 verified → `supported`. 0 verified → `insufficient_evidence`, scope "Quotes could not be verified against the bill text".
- If truncation happened, `scope_note` says so and the page shows "Drawn from the first part of a long bill".
- Bills without full text get no Bill Says row.
- In both cases (no full text, or `insufficient_evidence`), the page also shows the existing `what_it_does` claim below the state message, labeled "AI summary of the official description" — never presented as Bill Says itself.

### Staff section extraction (deterministic, no model)
- Uses the latest `staff_analyses` row for the bill that has text (by `analysis_date`, then `created_at`).
- "Effect of Proposed Changes": the Senate form `Effect of Proposed Changes:` is confirmed in production text; the House form is expected but unverified. Extracts up to the next known top-level heading.
- Fiscal impact: the Senate and House fiscal-impact sections and their state / local / private-sector subsections. The names above are expected from the standard formats, but the exact heading strings are **not yet verified**: the first implementation task samples real production analyses, records the actual headings, and builds fixtures from them (see Testing). Extraction matches only headings seen in those fixtures.

### Interpretation — `legislative_staff`
- Only when the latest analysis has an "Effect of Proposed Changes" section.
- Model condenses it to 2–5 plain-language statements, each with the bill `section_ref` it concerns. It must restate staff's reading only, with nothing added.
- Source: the staff analysis (`source_url`, committee, date). `scope_note` names committee and date.
- Analysis exists but has no such section → `insufficient_evidence`, scope "Staff analysis of <date> has no Effect of Proposed Changes section".

### Interpretation — `sunshine_ledger_ai`
- For every bill with full text, whether or not a staff analysis exists.
- Model interprets the bill text: 2–5 statements, each with `section_ref`, `assumptions` (must be non-empty or explicitly "none identified"), and `affected_groups` only when the text names them.
- Prompt rules: no value-judgment adjectives, no claims about intent or politics.

### Expected Effect — `legislative_staff`
- From the extracted fiscal sections. Each statement is a conditional restatement of staff's fiscal finding, with `assumptions` where staff state them.
- Staff "None" / "Indeterminate" / "Insignificant" are kept as literal statements ("Staff found the fiscal impact on local governments indeterminate"), not guessed at.
- No fiscal section → `insufficient_evidence` with scope.

### Expected Effect — `sunshine_ledger_ai`
- Only direct effects of a mechanism in the bill. Each statement must cite a `section_ref`.
- **Guards (code, not prompt):**
  1. `section_ref` must match a section heading present in the bill text (`Section N.` patterns); otherwise the statement is dropped.
  2. Statement must contain conditional wording (`may`, `could`, `might`, `is expected to`, `would`); otherwise dropped.
- 0 statements survive → `insufficient_evidence`, scope "No effects traceable to a specific bill section".
- No behavioral, economic, or systemic forecasts in this version.

### Selection and versioning
- For each (bill, layer, origin), compute the input hash. Skip if it equals the current row's hash; otherwise generate and insert a new version.
- Staff-derived rows hash the extracted section text, so a new committee analysis produces a new version; Sunshine Ledger rows hash the bill text, so they are independent of staff changes.

### Cost
First backfill ≈ 2,500 bills × up to 5 model calls (one per block; staff blocks only for the ~890 bills with analyses) on the Powerstation; run over several nights with `--limit`. After that, only changed bills are reprocessed nightly.

## API

`GET /bills/{id}` gains:

```json
"layers": {
  "bill_says":       [ <block> ],
  "interpretation":  [ <block>, <block> ],
  "expected_effect": [ <block>, <block> ]
}
```

Block: `{origin, current: <version>, earlier_versions: [<version>, ...]}`.
Version: `{version, evidence_state, review_status, reviewed_at, scope_note, items, generated_by, method_version, created_at, superseded_at, sources: [...]}`.

Also `has_staff_analysis: bool`, so the page can distinguish "No staff analysis published" from "Not yet evaluated".

`layer` and `origin` are fixed values from the backend. The frontend maps them to display text through one lookup table (`lib/layers.ts`). Blocks are placed by their key, never by position or content.

`claims` and every existing field are unchanged.

## Bill page

Replaces "What it does" and "Who it affects" **on the bill page only**, and only when the bill has at least one `bill_layers` row. Otherwise the current page renders unchanged. Browse cards, RSS, metadata, and sponsor pages keep using `claims`.

Order: Bill Says → Interpretation → Expected Effect, then Sponsors, Votes, and the rest as today.

Each section:
- Heading plus one-line definition:
  - Bill Says: "The bill's own words."
  - Interpretation: "What the change means."
  - Expected Effect: "What may happen. Forecasts, not established facts, and not legal or financial advice."
- Blocks stacked at every width: bill text / legislative staff first, Sunshine Ledger second.
- Origin badge written in text:
  - "Bill text"
  - "Legislative staff analysis · <committee>, <date> · condensed by AI" (neutral style, links to the PDF)
  - "Sunshine Ledger analysis · AI-generated" (distinct style)
  - Followed on every AI block by its review label (see "Human review"): "not reviewed by a person" or "reviewed by a person on <date>". The two review labels are visually distinct as well as worded differently.
- Items: statement; `section_ref` (linked to the full-text disclosure where possible); quote in a blockquote for Bill Says; "Assumptions" list; "Affected groups" when present.
- Block footer: model and method version, source date, last updated, and a `<details>` "N earlier versions" listing prior versions with dates.

Empty states (exact text):
- No row for this block: **Not yet evaluated.**
- Staff block when `has_staff_analysis` is false: **No staff analysis published.**
- `insufficient_evidence`: **Insufficient evidence**, followed by the `scope_note`.

Accessibility: correct heading levels (h2 layer, h3 block), badges readable as text, no meaning carried by color alone, layout checked at 375px width.

Methodology page: new section "Bill Says, Interpretation, Expected Effect" covering the three layers, the two origins, the verified-quote rule, the section-citation and conditional-language rules, and the meaning of each state.

## Testing

Backend (pytest, model mocked):
- Quote verification: exact and whitespace-variant matches kept; paraphrase, invented quote, and quote beyond the truncation point dropped; zero survivors → `insufficient_evidence`.
- Staff extraction: fixtures from real Senate and House analyses in `tests/fixtures/staff_analyses/`; section missing; fiscal "None"/"Indeterminate".
- Sunshine Ledger Expected Effect guards: nonexistent section dropped; non-conditional statement dropped.
- Versioning: changed input → new version, old superseded; unchanged input → no write; one current row per (bill, layer, origin), enforced by the DB index too; no update path on existing rows.
- States: no analysis → no staff rows; analysis without the section → `insufficient_evidence` with scope.
- API: `layers` shape, earlier versions, `has_staff_analysis`, disallowed (layer, origin) pairs rejected.
- Review: approving a current version makes it `reviewed` with a date; approving a superseded version returns 409; a new version supersedes a reviewed one and starts `not_reviewed` while the old version keeps its label; review endpoints require admin auth; `reviewer` and `note` never appear in the public API.

Frontend (vitest):
- Each block renders under its own layer heading and origin badge; a block keyed to one layer never appears under another.
- Empty states render with the exact text.
- Expected Effect disclaimer present.
- Earlier-versions expander lists prior versions.
- Review labels: an unreviewed AI block shows "not reviewed by a person"; a reviewed one shows "reviewed by a person on <date>"; Bill Says shows neither.
- Bill with no layer rows renders the current page.

Quality gate: `review_bill_layers.py` on ~20 real bills (mix of with/without staff analysis, state and local). The report includes quote pass rate and dropped effect statements. The user reviews it before the backfill.

## Rollout

1. Ship migration, pipeline, API, frontend, and methodology section together. No bill has rows yet, so nothing changes visibly.
2. Run the quality-gate report; user signs off.
3. Check mobile (375px) and accessibility in a browser against the local Docker stack, with layer rows (reviewed and unreviewed) seeded for a test bill. The gate run writes nothing to the DB, and anything written to production is immediately public.
4. Backfill in `--limit` batches over several nights, then enable the nightly step (copy `run-ingestion.sh` to docker-host).

## Out of scope

- A review UI (the admin endpoints are in scope; a page for them is not).
- Rejecting a version during review. Problems go through flags and the corrections spec.
- Correction change types and severity on versions.
- Evidence graph beyond this table (evidence taxonomy task).
- Behavioral/economic/systemic Expected Effects from Sunshine Ledger.
- Impact Lens relevance matching.
