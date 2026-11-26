# Privacy-safe usage counts (design, built dark)

Todoist `6j2w23fFJ2W4wfHG` (analytics and January value dashboard), Gate 1 (d) "privacy analytics baseline
defined with bot exclusions", Gate 4 (a, b). Draft 2026-11-25. **Switched off by default**: turning it on changes
a public promise on `/privacy` and is the owner's decision.

## The conflict this has to respect

`/privacy` says today: "It doesn't load any analytics or tracking scripts, and doesn't count or profile visitors"
and "No other page loads anything from a third party." Grant readiness needs a human-use baseline. The design
below counts **activity, not visitors**, so the promise changes from "doesn't count" to a precise, narrower
statement, and the third-party promise stays true.

## What is counted

Daily totals only, one row per (day, event, page kind):

| Event | Sent when | Answers |
|---|---|---|
| `page_view` | A page becomes visible in a real browser | How much the site is read, by page type |
| `bill_read` | A bill page has been visible for 15 seconds | "Verified bill detail reads" (ticket) |
| `source_click` | A reader follows a link to an official source (flsenate.gov, myfloridahouse.gov, LegiScan, Legistar, iQM2, congress.gov, clerk/House/Senate roll-call sites) | Whether readers check the record, the site's core claim |

`page_kind` comes from a fixed list: `home`, `browse`, `bill`, `person`, `district`, `map`, `promises`,
`corrections`, `methodology`, `other`. **No bill, person or district identifier, no search text, no topic, no
URL** is sent or stored: which bills someone reads is a political interest, and the ticket rules it out.

## What is never collected

No cookies, no local storage, no fingerprinting, no IP address, no user agent, no referrer, no identifiers of any
kind are stored. The request's IP is used only by the existing in-memory rate limiter and is not written.
No third-party script or service.

**Consequence, stated plainly:** with no identifier there are no unique-visitor, return-visit, first-week or
30-day retention numbers. Those need either accounts (watchlist activation, once accounts launch) or an opt-in
panel (the journalist pilot). The grant dossier must say so rather than estimate.

## Bot exclusion (layered)

1. **JavaScript only.** Counts are sent by the page's script, so crawlers that do not run JavaScript, the bulk of
   Cloudflare's request count, never appear.
2. **Automation flag.** Browsers driven by automation (`navigator.webdriver`) send nothing.
3. **Visible pages only.** Nothing is sent from prerendered or background tabs.
4. **Server checks.** The API drops requests with no user agent or one matching a crawler pattern, and requests
   whose `Origin` is not the site. The user agent is read for this check and discarded.
5. **Rate limit.** 60 events per minute per address (in-memory), so a loop cannot inflate the totals.

Residual risk: a headless browser that hides automation is counted. At this site's scale that is accepted and
disclosed; the totals are a floor for "activity by real browsers", not an audited audience figure.

## Baseline to publish (January)

Per week: page views by kind, bill reads, source clicks, and **source clicks per 100 bill reads** (the ratio that
says whether readers verify). Cloudflare's request counts stay a separate, labelled number (all traffic, bots
included) and are never added to these.

## Switches

* Backend `USAGE_COUNTS_ENABLED` (default false): off, `POST /usage` answers 404 and nothing is written.
* Frontend `NEXT_PUBLIC_USAGE_COUNTS_ENABLED` (default false): off, no request is ever made.
* `GET /usage/admin` (admin auth) returns the daily rows for the dashboard.

## Privacy page change (ready, apply only when switched on)

Replace "It doesn't load any analytics or tracking scripts, and doesn't count or profile visitors." with:

> The site keeps daily totals of three things: pages viewed (by type, such as "a bill page"), bill pages read for
> at least 15 seconds, and clicks through to official sources. These totals are counted by the site itself, with
> no cookie, no identifier and no record of which bill, person or place was viewed. Your IP address is used only
> to limit abusive request rates and is not stored. No analytics or tracking script from anyone else is loaded.

## Owner decisions

1. Switch on, with the privacy text above (or edited).
2. Whether the 15-second read threshold is right.
3. Whether weekly totals are published on the methodology page, or only in the grant dossier.
