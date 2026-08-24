# Nationwide Coverage Strategy (Local Government)

Roadmap, Nationwide Expansion: *"no unified local-government API exists
nationwide. Expansion should prioritize top metros and/or partnerships over
full county coverage."*

This is the strategy for that, grounded in what Phase 1 actually hit rather
than what the landscape looks like from a distance. Reconnaissance run
2026-08-23/24 against live APIs.

## The state layer is already solved

LegiScan covers all 50 states. Adding a state is a config change
(`LEGISCAN_STATE`) plus boundary data, not an integration. Nothing below
applies to state bills.

Local government is the entire problem.

## Finding: Legistar covers most large cities

Probed 20 of the largest US cities against the Legistar API:

| Result | Count | Cities |
|---|---|---|
| Confirmed on Legistar | **13** | Phoenix, San Antonio, Dallas, San Jose, Seattle, Denver, Boston, Oakland, Austin, Detroit, Atlanta, Miami, Jacksonville |
| Not found by guessing | 7 | New York City, Chicago, Los Angeles, Houston, Philadelphia, San Diego, Portland |

**The 7 are not confirmed absent.** They are cities whose client token we
failed to guess. That distinction is the single most important thing on
this page.

### Token discovery is the real blocker

Legistar identifies each client by an opaque token in the URL, and it is
routinely *not* the city name:

- Miami is `miamifl`, not `miami`
- Jacksonville is `jaxcityc`, not `jacksonville`
- Austin is `austintexas`, not `austin`
- Atlanta is `atlantaga`, not `atlanta`

Three of the eight "missing" cities were found simply by guessing a second
time. A wrong token returns HTTP 500 with *"LegistarConnectionString
setting is not set up in InSite for client: X"* — indistinguishable from
"this city isn't on Legistar" unless you know to read it that way. New York
and Philadelphia return 403, which suggests the client exists but is
access-restricted rather than absent.

So the per-city cost is not "build an integration". It is **find the
token** — a few minutes of manual work (check `<city>.legistar.com` in a
browser, read the redirect) that cannot be automated by guessing. Once
known, the existing `legistar.py` ingests it with a config entry.

**Practical implication:** one integration plausibly covers a majority of
the top 100 metros. Expansion should be sequenced as a token-discovery
exercise first, and only then as engineering.

## Finding: platform presence does not mean usable data

Miami is the cautionary case, and it cost real time in Phase 1.

Miami *is* on Legistar (`miamifl`) — the API answers, the token is right,
records come back. But there are only **six records**, all legacy, with no
sponsor data. Miami's actual current legislation lives on an entirely
different platform (Granicus iQM2), which required a separate HTML scraper.

A city being reachable proves nothing about whether the data is current.
**Always check record count and recency before declaring a city covered.**
A handful of stale records is arguably worse than none, because it looks
like success.

## Platform landscape observed

| Platform | Notes |
|---|---|
| **Legistar** (Granicus) | Best case. REST API, ~13/20 top cities confirmed. No text endpoint — `/Matters/{id}/Texts` returns 405; the ordinance is an attachment named "Original Bill" among exhibits. |
| **iQM2** (Granicus) | HTML scraping only. Miami's real source. Attachments are a privacy hazard — see below. |
| **eSCRIBE** | Orlando. Not yet evaluated. |
| **Municode** | Tampa. **Wrong shape entirely** — a codified-law repository, not a bill tracker. No amount of scraping makes it one. Don't spend time here. |

## Hazard: local attachments can contain personal data

Investigating full text for Miami, the document linked from an iQM2
legislation page turned out to be a scan of **public comment cards carrying
residents' full names and home street addresses** — not the resolution.

Ingesting that would put private addresses into the database and into
LLM-generated summaries on a public site. Any local-platform integration
must treat attachments as untrusted until the document type is verified.
This is a standing constraint, not a one-off: comment cards, minutes and
videos sit in the same attachment lists as legislation across these
platforms.

## Recommended sequencing

1. **Legistar cities first, by token discovery.** Cheapest coverage per
   hour of work by a wide margin. Batch the manual token lookup for the top
   50 metros, then add config entries. Verify record count and recency per
   city before counting it as covered.
2. **Fill obvious gaps case by case.** NYC, Chicago, LA, Houston and
   Philadelphia are large enough to justify bespoke work, but only after
   confirming what platform each actually uses — and whether an open-data
   portal (Socrata, CKAN) already publishes the legislation, which would be
   easier than any scraper.
3. **Partnerships over scraping for the long tail.** The Roadmap already
   calls for this in Phase 3, and the reconnaissance supports it: below the
   top ~100 metros, per-city engineering cost stays roughly constant while
   audience per city falls off sharply. Newsroom and open-data-city
   partnerships scale where scraping does not.
4. **Do not attempt full county coverage.** ~3,000 counties on
   heterogeneous or non-existent platforms. The Roadmap already rules this
   out; the data here supports that decision rather than revisiting it.

## Cost note

Local expansion is engineering-bound, not compute-bound. Summarization for
a whole additional city is a rounding error next to Florida's existing
corpus (see `docs/LLM_MODEL_ROUTING.md` — the entire 2,300-bill corpus
re-summarizes in about two GPU-hours). Do not let LLM cost drive local
expansion sequencing; token discovery and data verification are what cost
time.
