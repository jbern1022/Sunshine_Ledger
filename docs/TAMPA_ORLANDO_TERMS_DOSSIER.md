# Tampa and Orlando: what the sources say about automated reading

Status: facts gathered 2026-10-29 for the ruling in Todoist `6hm2FqXfHvxVR45G`. This is
evidence for the decision, not the decision. The vendors' public terms pages were read on 2026-11-10 (see "Vendor terms read" below);
the cities' own policy pages were not found (guessed URLs returned 404).

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

## Vendor terms read 2026-11-10 (still not a ruling)

Read from the vendors' public terms pages with an ordinary fetch. Quoted, not interpreted
beyond saying whose site each governs.

- **Hyland** (`hyland.com/en/legal/terms-of-use`, the terms for hyland.com's own websites)
  forbids to "Access or search the Site by any means other than our publicly supported
  interfaces (for example, "scraping")", and to use "any robot, spider, site search/retrieval
  application, or other manual or automatic device or process to retrieve, index, "data mine",
  monitor, or in any way reproduce ... the Sites or the materials". "The Site" here is
  Hyland's marketing and support website. Tampa's Agenda Online runs on a Hyland-hosted
  instance (`tampagov.hylandcloud.com`) for the city; whether these website terms, a separate
  product agreement with the city, or only the city's own policy govern that instance is **not
  stated on the page**. Do not read this as permission or as a ban on the Tampa portal. Ask the
  Tampa City Clerk (the city is the customer and publishes the agendas).
- **eScribe** (`escribemeetings.com/terms-of-use`) is a short page about eScribe's own website
  and trademarks. It contains no clause about automated access, scraping or robots. It says
  nothing about customer portals such as Orlando's `pub-orlando.escribemeetings.com`.
- Tampa's and Orlando's own website-policy pages were not found at the guessed URLs (404).

So: no clause found that forbids reading a city's published agenda portal, and none that
allows it. The one explicit anti-scraping clause found belongs to Hyland's own website.
That leaves the decision where the dossier already put it: proceed politely with the pacing
above, or ask the clerks first (recommended for Tampa given the Hyland wording).

## To finish before deciding

1. Open each hosted product's own terms (Hyland and eSCRIBE) and each city's website policy
   in a browser; paste the relevant clause here.
2. Confirm Orlando's agenda host has no robots.txt from a second network (a 404 can be a
   fluke of one request).
3. Sample one Orlando meeting's attachments and list the types that hold personal data.
