# Impact Lens: wiring the mapping step into the nightly

Status: **design, nothing wired.** Written 2026-11-10 on a local branch. Companion to
`IMPACT_LENS_REVIEW_LIFECYCLE.md` (what a reviewed, approved or rejected row does) and
`IMPACT_LENS_ROLE_LOCATIONS.md`. This note answers: what would it take to make
`python -m app.impact_lens.map_batch --pending` run every night, and what must be decided first.

## Where things stand

- The runner exists. `map_batch --pending [--limit N] [--max-minutes M]` maps every current,
  supported, uncapped Who-it-affects layer that still has unmapped entries at the current
  vocabulary and method version, newest bill activity first. A rerun makes no model calls for
  entries already mapped. One bad bill is counted and skipped. It exits 1 only if it failed
  everything and stored nothing.
- It is **not** in `scripts/run-ingestion.sh`. The docstring says why: wiring it publishes automatic
  mappings on every bill, which was waiting on a hand-labeled baseline.
- Readers do not see the lens by default. The bill page shows it only with `?lens=1`
  (`frontend/app/bills/[id]/page.tsx`). So storing mappings nightly changes nothing public until
  that flag is lifted; lifting it is a separate decision from this one.
- The read endpoint serves the newest mapping per entry at the current vocabulary version
  (`selection.py`). Unreviewed rows are served, labelled "Automatically mapped, not yet reviewed".
  Approved rows lose the label. Rejected rows are withheld and the bill's result cannot say
  "Does Not Appear to Apply".
- `review_tier()` in `criteria.py` classifies a mapping as `simple` or `needs_review`, but **nothing
  reads it at serve time**. Holding `needs_review` rows until approved is designed, not built.
- Any `METHOD_VERSION` or `VOCABULARY_VERSION` bump makes every entry "unmapped" again, so the
  first nightly after one maps the whole backlog, not one day's worth. Federal text and the
  v3 vocabulary already caused this once (method 10).

## What turning it on actually does

Per night, for each pending bill: one model call per Who entry (temperature 0, `num_predict` 2048,
seed from `LAYERS_SEED`), then the deterministic guards and the quote check. Cost is
entries x one local-model call. The model is the same Ollama host as Bill layers, so the two steps
compete for it; the nightly already holds a wall-clock budget for Bill layers (180 min) and
`--max-minutes` gives the mapper its own.

Things that are safe by construction: the step only inserts rows (no overwrite), reruns are
idempotent, a new method version inserts new rows rather than editing old ones, and a rejection
withdraws a row without deleting anything.

Things that are not yet settled:

1. **What the baseline must show before readers see unreviewed mappings.** The design says any
   `wrong` mapping that could flip a result blocks that bill's lens. `app.impact_lens.tally`
   counts hand-labeled verdicts (`correct`, `wrong`, `missed`, `unsure`) per part of a mapping. No
   labeled sheets are committed in the repo, so the current numbers are not on record here. The
   40-entry baseline mentioned in earlier notes never exercised a county condition.
2. **Whether unreviewed rows are shown at all** once the flag is lifted, or only `simple` ones.
3. **What happens to a bill when its Who layer is regenerated.** A new layer version has new
   `bill_layer_id`s, so every entry is pending again and earlier approvals do not carry over.
   Approvals attach to a row, not to an entry's wording.

## Options

| | A. Wire it as is | B. Wire it, hold `needs_review` rows | C. Keep it manual until a bar is met |
|---|---|---|---|
| Nightly step | `map_batch --pending` | same | none; run by hand per bill |
| Reader sees (behind `?lens=1`) | every mapping, labelled unreviewed | `simple` rows labelled; others treated as unmapped (result cannot say "does not appear") | only bills someone mapped |
| Build needed | one script line, one exit-code rule | serve-time tier filter, a "held" reason in `incomplete_reasons`, tests | none |
| Risk | a wrong complex mapping (exclusions, numbers, affected party) reaches readers, labelled | fewer bills reach a firm answer; backlog of held rows needs reviewers | coverage stays at a handful of bills |
| Fits the lifecycle doc | yes (current accepted display) | yes (the "separate decision" it names) | yes |

**Recommendation: B, and keep `?lens=1` until the baseline is read.** Mapping nightly is cheap and
harmless while the flag is off, it lets the review queue fill, and tiering holds back exactly the
rows where a wrong reading is most likely to flip a result. A is acceptable only while the flag
stays off. C wastes the pipeline's one advantage, which is that rerunning is free.

## What B needs, concretely

1. **Serve-time hold (backend).** In `selection.py` / `api/impact_lens.py`, a row with
   `review_tier(criteria) == "needs_review"` and no approval is returned as `criteria: null`,
   `held: true` (a new field, distinct from `withdrawn`), and counted in `incomplete_reasons`
   ("N entries are waiting for review"). The matcher already treats `criteria: null` as unknown.
   Tests: held row never yields "Does Not Appear to Apply"; approving it releases it; rejecting it
   still wins; `simple` rows are unaffected.
2. **A review queue listing.** `app.impact_lens.review` lists one bill. Add `--queue` to list held
   entries across bills, ordered by bill activity, so a reviewer works the newest first.
3. **The nightly line.** In `scripts/run-ingestion.sh`, after Bill layers (it maps the layers that
   step produces) and before the Federal steps:
   `step "Impact Lens mapping" docker exec "$CONTAINER" python -m app.impact_lens.map_batch --pending --limit 200 --max-minutes 60`.
   A non-zero exit follows the existing `step` convention (counted as a failed step, pings once).
4. **Backlog guard.** After a method or vocabulary bump the first run would face the whole
   backlog. `--limit` and `--max-minutes` already bound it, newest first, so the backlog drains
   over several nights. The step logs "N bills still pending" so progress is visible.
5. **Freshness note.** Record the last successful mapping run in `source_checks` (as `record_partial`
   does for crawls) so `/sources/status` can say mapping is behind rather than silently stale.

Rough size: items 1 to 3 are about a day of backend work with tests; 4 and 5 are small.

## What stays a person's job

- Approving or rejecting held rows (`review --approve/--reject`).
- Reading the baseline tally and deciding when `?lens=1` goes away.
- Ruling on whether `local_government` and similar roles use the residence location
  (open question in `IMPACT_LENS_ROLE_LOCATIONS.md`).

## Decisions needed

1. Option B as recommended, or A or C?
2. Is `simple` the right line for what may show unreviewed, or should it be narrower (for example,
   audience plus a single county test only)?
3. The bar for removing `?lens=1`: a number of hand-labeled entries with zero `wrong`, or
   something else?
4. Budget for the mapping step each night (60 minutes proposed) given it shares the model host with
   Bill layers.
