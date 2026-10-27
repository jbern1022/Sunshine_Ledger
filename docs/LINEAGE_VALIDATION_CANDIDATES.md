# Legislative-lineage validation: candidate source pairs (first pass)

Status: draft for Joe's review, 2026-10-26. Todoist `6hWgXrg44mp3PVHG`; plan: Notion
"Identity, Relationships & Legislative Lineage - Combined Validation Plan". This is a
**candidate list with what was and was not verified**, not an executed validation. Nothing
here says any bill was copied; the methodology says similarity alone is insufficient and
separates exact text, provenance, chronology, documented receipt/use, drafting
assistance, policy alignment and influence.

Expected results below were written **before** any text comparison and are not blind
(I read the secondary sources first). Do not edit them to match later results.

## Pair 1: Florida "Stand Your Ground" (2005) and ALEC's "Castle Doctrine Act" model

- **Why it is a good test:** the direction is the opposite of the usual assumption. The
  model was built **from** the Florida law, so a "Florida adopted the model" claim would
  be wrong. It tests chronology and the rule that similarity does not show direction.
- **Verified (retrieved today):** the Florida Statutes history line for s. 776.013 reads
  "s. 1, ch. 2005-27; s. 4, ch. 2014-195; s. 1, ch. 2017-77", so ch. 2005-27 is the
  original enactment. A RAND summary and ALEC Exposed state that ALEC's model is based on
  Florida legislation enacted 2005-04-26.
- **Secondary only:** The Nation says that after Florida's law was signed a legislator
  worked with NRA operatives and members of ALEC's Criminal Justice Task Force to draft
  the model. ALEC Exposed reproduces model language (no duty to retreat, civil immunity,
  limits on arrest). RAND notes that some later state laws strayed from the Florida text.
- **Not verified:** the ALEC adoption date from an ALEC primary record; the model's own
  text (ALEC Exposed is a reproduction); the session-law text of ch. 2005-27; the bill
  number (HB 249 was my guess and was not confirmed); a text comparison.
- **Expected result:** *Provenance runs Florida to model. Text overlap in the core
  provisions is expected; direction is established by chronology, not by the overlap.
  Receipt of ALEC language by the Florida Legislature: not supported (it preceded the
  model).* Classify "documented policy-language use" only for **other** states' enactments,
  and only with their own provenance.
- **Needs:** the session law, ALEC's published model with its date, then a provision-level
  comparison for Florida and for one later state to show the contrast.

## Pair 2: SB 1896 (2011), a Florida sanctuary-city bill, and ALEC text

- **Source of the claim:** a Progress Florida report (advocacy) says ALEC model
  legislation has been introduced in Florida "at times word for word" and names SB 1896
  (2011) as modeled on ALEC text.
- **Verified:** nothing yet. I did not retrieve the bill, the model, or the report's page
  number. It is an advocacy source, so it is a lead, not evidence.
- **Expected result:** *Cannot determine until a text comparison and documentary
  provenance exist. If wording overlaps, the finding is "similar text", not "language was
  provided by ALEC", unless a document shows receipt or use.*
- **Needs:** the SB 1896 text and history from the Legislature, the candidate model(s)
  with dates, a provision comparison, and any documented receipt (correspondence,
  testimony, a sponsor statement). Note SB 1070 (Arizona, 2010) also exists as a possible
  common ancestor, which makes direction a real question.

## Pair 3 (negative control, not yet identified): identical wording from standard definitions

- **Why:** the USA TODAY / Arizona Republic work warns that identical language can come from
  standardized definitions (its example is the definition of an opioid), not copying. The
  methodology needs a case where overlap is high and the correct result is "no finding of
  use."
- **Needs:** a Florida bill whose overlap with a model is limited to boilerplate or a
  uniform-law definition. The public model-bill dataset behind the USA TODAY /
  Center for Public Integrity "Copy, Paste, Legislate" work lists Florida bills with
  similarity scores and could supply this; I did not retrieve it.

## Method notes from the first pass

- Chronology and direction must be checked **before** text similarity; the Stand Your
  Ground case would be misread by a similarity-first tool.
- Record the source tier of each fact (statute history line and Clerk records are
  primary; ALEC Exposed, Progress Florida and The Nation are advocacy or secondary).
- A provision-level comparison needs both texts at a stated version and date. The app
  already stores bill text versions (`bill_text_versions`) for Florida bills, so the
  Florida side can come from the database; the model side has no home in the schema.
  That is an engineering gap to record, not to build yet.
- Out-of-state enactments (RAND: "strayed further from the Florida and Utah statutes")
  show that "same model" is not one yes or no per state; compare per provision.

## What would complete this

1. Retrieve ch. 2005-27 text, the ALEC model with a primary date, and SB 1896 (2011)
   text and history.
2. Find the negative-control pair from the public dataset.
3. Run the comparisons, record actual against expected, and fill the validation record
   in Notion (that step is yours to approve).
