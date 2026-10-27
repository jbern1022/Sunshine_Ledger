# How local-government items read on the live site (2026-10-27)

Todoist `6hm2FqVh66Mmww6G`. Read-only review of the public API
(`/bills?jurisdiction_name=<place>&limit=100`) for all 32 places with records:
3,200 items (the 100 newest per place). Checked that the filter returns only the
requested place (0 of 3,200 from another place). No production host access.

## Findings

1. **Summaries call every local item "this bill" (84%).** 2,697 of the 3,200 `what_it_does`
   texts contain "This bill" or "the bill", including 1,685 of 1,848 items classified `other`,
   210 of 222 `agenda` items and 89 of 99 `discussion` items. Cause: `summarize.py`'s
   `WHAT_IT_DOES_PROMPT` opens "You are summarizing a piece of legislation" and is used for
   every `item_kind`. Examples: an Orange County public-hearing case number ("Case # LUP-26-02-020 ...
   Gotha Subdivision") is summarized as "This bill proposes a land use plan"; a Polk County consent-agenda
   request to opt in to a settlement is "This bill asks the County Board ...". The methodology page promises
   summaries that stay within the text and avoid speculation about intent.
2. **Records with almost no content get an invented meaning.** Key West minutes titled
   "October 21, 2026" are summarized "The bill makes a change to a specific date". Minutes and
   matter-number titles ("Matter 7218", "10-13 Minutes"): 35 items in the sample; 18 have no summary at all,
   so the card shows only the number.
3. **Hedging and place errors.** 344 of 3,200 summaries (10.7%) contain "likely", "appears to",
   "seems", "presumably" or "probably". One Orange County hearing summary says the planned
   development "is a specific area of the city" (it is a county item).
4. **Titles carry source clutter.** 63 Jacksonville titles end with history text such as
   "10/27/26 CO Introduced: R", and many titles across places contain raw `\r\n` (first line a case number,
   then the applicant). HTML collapses the line breaks, so the case number and applicant run together.
5. **Kind mix differs sharply by place**, which is expected but worth stating on the site: Jacksonville
   and Miramar are 100% `legislation` in this sample; Orange County is 99 `other`, 1 `legislation`
   (its agenda is mostly public-hearing cases); Polk is 69 `agenda`.
6. **One future date.** A Pinellas County item (status "Final") has `last_action_date` 2026-11-17, after
   the review date. Probably a meeting date; check the field's meaning before presenting it as "last action".

## Recommended changes (not made)

- Kind-aware summary prompts: for `agenda`, `discussion` and `other`, describe "this item" or "this
  agenda item", state what the record is (hearing case, minutes, request), and say "no further detail is
  published" instead of guessing. Skip the summary for minutes and bare matter numbers and show the record
  type instead. Bump the prompt version so the nightly re-summarizes only local non-legislation items.
- Add a post-generation check that rejects "bill" wording on non-legislation and hedging words, as the layers
  already do for unsupported quotes.
- Normalize titles at ingest: replace `\r\n` runs with " - ", strip a trailing "MM/DD/YY XX Introduced" tail
  (Jacksonville), keep the original in metadata.
- Methodology page: add one sentence saying local records include hearing cases, agenda items and
  minutes, not only legislation.
- Rename or document `last_action_date` for scheduled meetings.

## Method

Per place: item_kind counts; regex `\b(this|the) bill\b` on `what_it_does`; hedging words; CRLF in `name`;
`last_action_date` after 2026-10-27. The sample is the newest 100 items per place, not a random sample.
