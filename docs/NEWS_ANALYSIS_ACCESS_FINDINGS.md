# News analysis: article access and GDELT availability (findings, 2026-11-10)

Todoist `6hrmjg4JPMGpChGp`. Companion to `GDELT_TONE_OPTIONS.md` (2026-10-21) and
`NEWS_ANALYSIS_SCHEMA.md`. This records what was checked today, what was not, and a recommended
route. No ingestion, spending, outreach or production change was made. One request was sent to GDELT
(below), and no egress was rotated.

## What was checked, and when

| Check | Result (retrieved 2026-11-10) |
|---|---|
| One request to the DOC 2.0 API (`mode=ArtList`, 3 records, a descriptive user agent, from the owner's current network) | **HTTP 429.** The body says: "Please limit requests to one every 5 seconds or contact [GDELT's operator] for larger queries. All high-traffic users should switch to our ngrams dataset", and points to the daily trends briefings. It was a single request, so the 429 is not explained by our own rate; the throttle on this address is still in place. I did not retry. |
| `http://data.gdeltproject.org/gdeltv2/lastupdate.txt` | HTTP 301 (to https). The file feed is reachable; the file contents were not downloaded. |
| GKG 2.1 codebook (PDF, 61k characters of text) | Read. Tone definitions below. |
| GDELT "Terms of Use" (about page) | Read. Quoted below. |

## What GDELT's tone fields measure (from the GKG codebook)

The GKG tone field is a document-level summary of the **wording**, computed from a **tonal
dictionary** of words, not from any reading of meaning:

* **Tone**: "the average 'tone' of the document as a whole", from -100 (extremely negative) to +100
  (extremely positive); "common values range between -10 and +10". It is Positive Score minus Negative
  Score.
* **Positive Score / Negative Score**: the percentage of all words that matched a positive (or negative)
  emotional connotation. (The codebook's own text for Negative Score says "positive"; this is a typo
  in the source and is noted here so nobody builds on it.)
* **Polarity**: the share of words that matched the tonal dictionary at all, "an indicator of how
  emotionally polarized or charged the text is". High polarity with neutral tone means lots of charged
  words that cancel.
* **Activity Reference Density**, **Self/Group Reference Density** (pronouns), **Word Count**.

What this means for us: the number says how emotive the **whole article's vocabulary** is. It does not
know what the article is about, who is speaking, or what position is taken on **our bill**. An article
about a tragedy a bill would prevent scores negative. **Tone must never be equated with stance**, as the
ticket requires; a GDELT tone is at most a coarse, article-level context figure, never an input to a
stance label.

## What is and is not available

* **GKG records carry an identifier for the document** ("the unique external identifier... URLs of open
  web resources", or a citation for print), plus extracted themes, people, organizations, locations,
  quotations metadata and the tone fields. **They do not carry the article text.** Full text must come
  from the publisher.
* **The DOC API** is throttled on this network (above), documents no rate guarantee beyond the message
  quoted, and per the earlier note does not document returning a per-article tone from `ArtList`.
* **Not checked:** BigQuery pricing and access; the GCAM codebook; publishers' terms and robots.txt;
  the daily trends briefings the 429 message mentions; whether a polite once-every-5-seconds client
  from a different network would be accepted (we must not try other egress to get around the throttle).

## Terms (GDELT's own, retrieved 2026-11-10)

"...all datasets released by the GDELT Project are available for unlimited and unrestricted use for any
academic, commercial, or governmental use of any kind without fee." Redistribution is allowed but "any
use or redistribution of the data must include a citation to the GDELT Project and a link to this
website (https://www.gdeltproject.org/)". No license identifier is named. These terms cover GDELT's
**data**, not the publishers' articles that the URLs point to.

## The real constraint: article text belongs to the publishers

Reading, quoting and keeping an article is governed by each publisher's terms and by copyright, not by
GDELT. Until those are checked outlet by outlet, the safe design is:

1. Keep **URL, title, date, outlet, and the short passages the analysis cites** (quotes of the
   length a citation needs), not a stored copy of the article.
2. Fetch article text only where the site's robots.txt and terms allow it, with the same polite,
   paced, capped fetcher as the promises crawler, and mark every record `headline_only`, `partial_text`
   or `full_text` truthfully (schema).
3. Where the text cannot be fetched or kept, the analysis abstains or is headline-only and says so.
4. Record, per outlet, the terms reviewed and the date, so the sample can be audited.

## Recommended route (a proposal; the owner chooses)

1. **Discovery from the GKG files**, not the DOC API: the 15-minute CSV files are public, are not
   subject to the DOC throttle, and give URL, date, outlet, themes and organizations to match against
   our bills. Pull them in bulk on a schedule, keep only rows that match a bill's name or sponsors, and
   cite GDELT as the source. This avoids the throttled endpoint entirely and needs no BigQuery.
2. **Article text** by the polite fetcher, per the rules above, for the **benchmark sample first**
   (about 30 items to pilot the rubric) before any pipeline exists.
3. **GDELT tone**: do not use for stance. If shown at all, it is an article-level context figure,
   labeled as a dictionary-based wording measure, and still gated by the public-label review.
4. **BigQuery**: only if the file feed proves too heavy; needs a Google account, a budget cap and the
   owner's approval. Not recommended now.

## Costs and limits to confirm

Bandwidth and storage for the GKG files (large; filtering on the fly keeps only matches); no per-call
fees for the files; fetching article pages costs only our own bandwidth and time at the polite pace.
These are expectations, not measurements: a one-day trial pull of the files would measure them.

## Open

* Per-outlet terms for the outlets that cover Florida bills, and the retention and quotation limits that
  follow.
* Whether to email GDELT's operator about the throttled address (the 429 message invites it). That is
  outreach and is the owner's call.
* Whether the GKG's organization and theme fields are good enough to match articles to bills, to be
  measured on the pilot sample.
