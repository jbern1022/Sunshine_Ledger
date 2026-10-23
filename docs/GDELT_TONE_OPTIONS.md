# GDELT tone and stance: what is possible, and what to decide

Status: research note, 2026-10-21. Roadmap Phase 2 lists "Full GDELT tone/sentiment +
stance classification (currently thin, unscored headlines only)". Nothing here is built.

## What the current pipeline has

`backend/app/pipeline/gdelt.py` calls the DOC 2.0 API in `ArtList` mode and stores a
few recent headlines per bill. No score of any kind. The weekly run is paused while the
home IP is rate-limited by GDELT (see `docs/DATA_SOURCES.md`).

## What GDELT documents (checked against GDELT's own posts, 2026-10-21)

Source: <https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/> and
<https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/>.

- DOC 2.0 modes include `ArtList`, `TimelineTone` and `ToneChart`. Tone is available as
  a **filter** (`tone>`/`tone<`), a **sort** (`ToneDesc`/`ToneAsc`) and as **aggregates**
  (`ToneChart` bins coverage from -100 to +100). The post does not say that `ArtList`
  returns a per-article tone number, so we should not assume it does.
- `ArtList` returns up to 250 records; `TIMESPAN` defaults to 3 months and the start
  date must be within the last 3 months.
- No rate limit is documented. Our own observed 429s are the only evidence.
- The GKG (Global Knowledge Graph) is published every 15 minutes as CSV files
  (`data.gdeltproject.org/gdeltv2/`, with `masterfilelist.txt` and `lastupdate.txt`)
  and as the BigQuery table `gdeltv2.gkg`. The GKG carries a tone field per article
  (V2Tone), but the posts above do not define its numbers; the GKG codebook does, and
  was not read for this note.

## Options

1. **Aggregate tone only (smallest).** For each bill, call `TimelineTone` / `ToneChart`
   for the same query and store the coverage-level distribution. No per-article claim and
   no model, but it is still a score attached to a bill, so see "Doctrine" below.
2. **Per-article tone from the GKG.** Match our stored article URLs to GKG rows and keep
   the tone GDELT already computed. Needs either the 15-minute files (a lot of data to
   scan) or BigQuery (a Google account and costs). Not rate-limited like the DOC API.
3. **Stance classification with our own model.** Ask a local model whether a headline
   supports or opposes a bill. Highest risk (below), and headlines alone are a weak input.

## Doctrine and legal constraints (why option 3 is not a quick win)

- BRD 5.8 and the Trust & Accountability Doctrine rule out composite scores and
  predictive claims; the roadmap already struck the "rhetoric consistency score".
- The roadmap requires a legal review checkpoint before launching electioneering-adjacent
  features. A stance label on coverage of a bill that a candidate sponsors is close to it.
- Sentiment of a headline is not stance toward a bill (a negative headline can report
  harm the bill would fix). Any label would need disaggregated display and error rates
  measured on a hand-labeled sample first, like the Impact Lens baseline.

## The blocker either way

The DOC API is throttled from the home IP. Options: email GDELT (Joe), run the pull
from a different egress, or switch to the GKG/NGrams data (options 2 above).

## Decisions for Joe

1. Is any score on news coverage acceptable under the doctrine, or should the news layer
   stay unscored? If unscored, close the roadmap item as "won't do".
2. If scored: aggregate tone only (option 1), or per-article tone from the GKG (option 2)?
3. Stance classification: defer until after the Phase 3 legal review?
4. Unblock the data: email GDELT, or move to GKG/BigQuery?
