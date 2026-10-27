# Impact Lens: review lifecycle for criteria mappings

Todoist `6hrFRCWHQGGQjpwp` (under `6hhJ73hVHcx9RpGG`). Applies to rows of
`bill_layer_criteria` (how a reader's answers are tested against one Who it affects entry).

## States of one mapping row

| State | How it is reached | What readers get |
|---|---|---|
| unreviewed | no review rows | criteria served, labelled "Automatically mapped, not yet reviewed" (unchanged) |
| approved | an `approved` review row, no `rejected` one | criteria served without the unreviewed label |
| rejected | any `rejected` review row | criteria **withheld**: `criteria` is null and `withdrawn` is true |

Rules:

- **Rejection is terminal for that row and beats approval.** A person who rejects a mapping after
  approving it is correcting an earlier mistake; reviews are append-only, so both rows stay on record.
  A rejected row cannot be approved. To bring the entry back, remap it: a new method or vocabulary
  version inserts a new row, which starts unreviewed.
- **A withdrawn entry is an unmapped entry.** The matcher already treats `criteria: null` as unknown, never
  as "does not apply", and the endpoint's `complete` flag goes false with its own reason
  ("N entries were withdrawn after review"), so the headline cannot say "Does Not Appear to Apply".
- **No fallback to an older row.** If the newest row is rejected the entry shows as withdrawn; an older
  row from a previous method is never served in its place.
- **Rejecting a mapping is not deleting a disputed public claim.** The Who entry itself (the quote and text)
  is untouched; only the derived question mapping is withheld. Disputes about the Who entry go through
  the correction process (`flags`, `correction_records`).

## One selection rule

The read endpoint and the review CLI now use the same function (`app/impact_lens/selection.py`): the
newest row per entry at the current vocabulary version, whatever its method version. Before, the CLI
also required the current method version, so after a method bump an approval could land on a row readers
were not being served, or the CLI showed "not mapped" for entries readers saw.

## Not changed

Nightly mapping stays unwired and the "labelled unreviewed" display stays as accepted. Holding
`needs_review` mappings until approved is a separate decision (`review_tier` in `criteria.py`).
