# Accuracy samples 01 + 02, re-run on the same records (2026-11-27)

Todoist 6j5FfXR8WmXjf3Vp. A paired before-and-after check of the same 40 records after the 11-26/27
re-summarize nights:
- the local prompt `2+local1`, which names the instrument and jurisdiction and keeps conditions
- the state prompt `2+state1`

**Method.**
- Same template (`SOURCE_TO_CLAIM_AUDIT_TEMPLATE.md`), severity rules and sources as the 11-25 audits: full text where the API has it, otherwise the official title (local) or the act title (state), with **U** for a detail the source checked doesn't cover.
- Every record's summary carries the current prompt's input hash; checked in the database 2026-11-27.
- Summaries are rewritten in place, so `created_at` still shows the first-written date. That date can't be used to tell whether a record was regenerated.

**Still a single AI auditor checking AI-written text, so these are not publishable figures.** A human
second auditor should re-check at least 25% of sentences first, starting with the records marked major
below.

## Results

| | Sentences | Critical | Major | Critical + major | U | Wording defects (minor) |
|---|---|---|---|---|---|---|
| **Local, before** (11-25) | 57 | 2 | 12 | **14 (25%)** | 10 | "bill" for a local instrument in 16 of 20 |
| **Local, after** | 42 | 0 | 4 | **4 (10%)** | 8 | 0 of 20 |
| — with full text (6) | 16 vs 19 before | 0 vs 0 | 0 vs 1 | 0% vs 5% | 0 | |
| — title only (14) | 26 vs 38 before | 0 vs 2 | 4 vs 11 | 15% vs 34% | 8 | |
| **State, before** (11-25) | 67 | 1 | 6 | **7 (10%)** | 11 | "bill" for a joint or simple resolution in 2 |
| **State, after** | 67 | 0 | 5 | **5 (7%)** | 27 | 0; but 3 of 20 open with "Here is a 2-4 sentence summary of the bill:" |

How to read this:
- **Local summaries improved clearly.** The critical wrong-party error ("the state" for Margate) and the "bill" wording are gone.
  - Title-only summaries are shorter and stay closer to the title, at about 1.9 sentences each vs 2.7 before.
- **State summaries improved a little.** Most of the change is that the H.B. 683 critical is gone, along with two dropped-condition majors and two invented-purpose majors.
  - The H.B. 7019 sunset logic is still inverted, and two new majors appeared.
  - **U** rose because the new summaries carry more detail from the bill text than the act title lists. That's expected, not a defect, but it means a text-based check (not a title-based one) is needed to score them.
- With n = 20 per stratum the intervals are wide. Read the direction, not the decimals.

## Findings that remain (critical or major)

| Sample | # | Record | Finding | Check | Severity |
|---|---|---|---|---|---|
| 01 | 2 | Miramar R8649 | "appointments to various **advisory** boards": the title says "Board Appointments" only | C1 | major |
| 01 | 10 | Miami R-26-0321 | "**requires** the Executive Director to submit"; the title **authorizes** it | C2 (modality) | major |
| 01 | 13 | Margate 2026-319 | "Margate **has agreed** to a contract": the resolution **approves** the agreement; adoption isn't shown | C2 (status) | major |
| 01 | 15 | Miami R-26-0331 | "authorizing its City Manager to accept grant funding": drops "**if awarded**" | C3 (condition) | major |
| 02 | 4 | H.B. 7019 | "will remain in place **unless it is repealed** by the Legislature on October 2, 2031": still inverted. It **repeals** on that date **unless reenacted** | C2 | major |
| 02 | 6 | H.B. 683 | No longer says supervision is removed (was critical). It restates existing prescribing rules and **omits both changes the bill makes** (no DOH notice; no supervisor's name on the prescription). "May not **dispense** medications listed on a formulary" misstates the formulary, which lists drugs they may not **prescribe** | C2, C3 | major |
| 02 | 8 | S.B. 1758 | "The Florida legislature **has passed** a bill": it **died in messages** | C2 (status) | major |
| 02 | 10 | S.J.R. 282 | "assessed value … may not exceed **3% of the prior year's assessment**": the cap is on the annual **increase** | C2 | major |
| 02 | 19 | S.B. 556 | "does not change any existing requirements for students without disabilities": the marching band substitution applies to all students | C2 | major |

Fixed since 11-25:
- Local #5, 6, 7, 9, 17, 18 (purposes, definitions, "has ratified", "buy", "tax", "helps save") and #13's critical.
- State #2, 12, 17, 18 and #6's critical.

## What to do next

1. **Preamble:** 2,168 state and federal summaries open with "Here is a … summary". Fixed on branch `fix/summary-preamble-and-key-logging`, with a one-off backfill (no re-summarize).
2. **Sunset logic (H.B. 7019):** the state prompt fix didn't take.
   - Open Government Sunset Review bills follow one formula, so use a fixed rule-based sentence for them ("The exemption is repealed on DATE unless the Legislature reenacts it") instead of asking the model.
3. **Status words:** "has passed", "has agreed", "is now renamed".
   - Summaries describe what a measure does, not whether it passed. A status check like `overstates_modal` (status words in a summary when the record isn't enacted or adopted) would catch #8, #13 and the state "now" phrasing.
4. **Modality and dropped conditions on title-only local items** (#10, #15): extend the `overstates_modal` guard to `what_it_does` ("authorizing" → "requires"; "if awarded" dropped).
5. **Re-score the state stratum against the bill text, not the act title**, before publishing anything. Most of the new **U** are probably correct details from the text.
