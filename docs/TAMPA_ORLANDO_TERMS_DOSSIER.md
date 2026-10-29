# Tampa and Orlando: what the sources say about automated reading

Status: facts gathered 2026-10-29 for the ruling in Todoist `6hm2FqXfHvxVR45G`. This is
evidence for the decision, not the decision. **No terms-of-use text was read**: the guessed
policy URLs on tampa.gov and orlando.gov returned 404, and a terms page for the two hosted
products (Hyland OnBase Agenda Online, eSCRIBE) needs a browser session to locate.

## Findings

| Question | Tampa (OnBase Agenda Online) | Orlando (eSCRIBE) |
|---|---|---|
| Host | `tampagov.hylandcloud.com/251agendaonline` (answers 200) | `pub-orlando.escribemeetings.com` (answers 200) |
| robots.txt on that host | None (404): nothing is disallowed or rate-limited there | None (404): same |
| robots.txt on the city's main site | `tampa.gov/robots.txt` exists, standard CMS rules, one sitemap line, no `Crawl-delay` | `orlando.gov/robots.txt` is 3,907 lines of `Disallow:` for forms, confirmation pages and draft pages; none of the lines checked names the eSCRIBE host or the agenda pages |
| Structured data | Meeting list as JSON in the search page; agendas as documents | HTML only, no API found |
| Record level | Meeting-level (agenda documents), not matter-level | Meeting-level, with attachments |
| Known privacy risk | Not yet inspected | Attachments can include public-comment cards with private home addresses |
| Terms of use | **Unread** | **Unread** |

For comparison, every iQM2 tenant publishes `Crawl-delay: 60` (miamifl.iqm2.com/robots.txt),
which is the open pacing question in `6hrFq2mH5Pj68qgG`. Neither Tampa's nor Orlando's agenda host
states any pacing.

## What this does and doesn't settle

- The technical signal (robots.txt) does not forbid reading either agenda host. It is
  silence, not permission.
- Whether the product terms or the city's website terms restrict automated access is unknown
  until someone reads them.
- The privacy issue for Orlando is independent of terms: an adapter would have to skip
  comment cards and any attachment type that holds residents' addresses.

## If the decision is to proceed

Build it as the existing scrapers are meant to behave: an identifying User-Agent with a contact
address, a fixed delay (default 10 seconds, configurable), a per-run cap on requests, no
retries on 403/429, and a visible stop switch. Tampa first (JSON, fewer unknowns); Orlando
only with the comment-card filter and a test for it.

## If the decision is to ask first

Email the Tampa and Orlando City Clerks (their offices publish the agendas). A short note
stating the purpose (a public civic-records site), the schedule (nightly, low rate) and an
offer to follow whatever pacing they name. Keep their reply in this folder.

## To finish before deciding

1. Open each hosted product's own terms (Hyland and eSCRIBE) and each city's website policy
   in a browser; paste the relevant clause here.
2. Confirm Orlando's agenda host has no robots.txt from a second network (a 404 can be a
   fluke of one request).
3. Sample one Orlando meeting's attachments and list the types that hold personal data.
