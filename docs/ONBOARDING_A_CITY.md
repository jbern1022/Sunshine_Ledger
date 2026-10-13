# Onboarding a Legistar city or county

The expansion test (Roadmap, "Florida-completeness gate") is whether the next
jurisdiction can be added through configuration instead of new product code.
For a Legistar jurisdiction, it can: this is the whole procedure.

## 1. Find the client token

Tokens aren't guessable from the city name (`jaxcityc`, `miamifl`). Try
`python3 scripts/probe_legistar_tokens.py --only "<Place>"`, or open
`https://<guess>.legistar.com` in a browser and read where it lands. A wrong
token 500s with `LegistarConnectionString ... not set up in InSite`.

## 2. Check the client is real, Florida and current

All three, before it counts as coverage:

- **Florida.** The probe's `likely_florida` flag (2+ matters citing "Florida
  Statutes" or "F.S."). Tokens collide across states: `madison` is Madison,
  WI; `oakland` is Oakland, CA; `jacksonco` is Jackson County, MO.
- **Current.** `newest_matter` within the last weeks. `miamifl` answers but
  holds six stale records; the real data is on iQM2.
- **Is the primary system.** A city can run Legistar for one board and
  something else for its council.

## 3. Add one registry entry

`CLIENT_JURISDICTIONS` in `backend/app/pipeline/legistar.py`:

```python
"fortlauderdale": {
    "jurisdiction": "Fort Lauderdale",   # Entity.jurisdiction_name, the site's filter value
    "county": "Broward County",          # geo scope, drives the area context
    "nightly": True,                     # ingest in the nightly run
    "label": "Fort Lauderdale City Commission (Legistar)",
    "note": "...",                       # the known-gaps line on the methodology page
},
```

Counties add `"level": "county"` and a `"publisher"`. Optional settings, each
added only when the client's data needs it (Fort Lauderdale and Broward show
why; check a sample of its feed first):

- `text_attachment`: regexes for the attachment that is the legislation
  itself (clients name them differently; the default is Jacksonville's
  "Original Bill").
- `body_sponsors_as_committees`: the client's sponsors are meeting bodies, not
  people.
- `item_type_from_title`: the client's own types are agenda categories
  ("Consent Item"), so the record kind comes from the title (Broward).
 The nightly step,
`/sources/status`, per-city counts, the bill-page freshness note and the
methodology source list all read this registry.

## 4. Frontend touchpoint

Add the city to `LOCAL_JURISDICTIONS` in `frontend/lib/jurisdictions.ts`. The
homepage dropdown reads the live source list, but the location proxy (which
sends a visitor in that city to its bills) and the dropdown's fallback use
this constant.

## 5. Test, then deploy

Add a registry test next to `test_ingest_fort_lauderdale_is_a_registry_entry_only`
in `backend/tests/test_legistar_tagging.py`. Then, in this order:

1. Merge to main (Woodpecker tests and deploys; the backend container is
   recreated, so stop docker-exec jobs first).
2. Copy `scripts/run-ingestion.sh` to `joe@docker-host:~/scripts/` only if it
   changed, and never before the code that it calls is deployed.
3. First run by hand and spot-check:
   `docker exec sunshineledger-backend-1 python -m app.pipeline.legistar --client <token> --limit 200`
4. The next nightly run ingests it; check `/sources/status` shows its check date.

Bill text is a separate nightly step ("Legistar bill text", newest first,
100 a night; an item with no usable attachment is re-checked after 14 days).

New cities start with the most recent N matters (`--limit`), not full history.
Historical backfill is a separate step.
