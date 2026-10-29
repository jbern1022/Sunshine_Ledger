/** English message catalogue: the reference for every other language.
 *
 *  Keys are flat and dotted. `{name}` is replaced by a parameter. A key with
 *  `.one` / `.other` (and `.zero` / `.two` / `.few` / `.many` when a language
 *  needs them) is a plural, chosen by the `count` parameter.
 *
 *  Wording here is the site's current English, moved verbatim. A new language
 *  must define the same keys with the same `{placeholders}`
 *  (lib/i18n/catalog.test.ts enforces it) and ships only after a fluent reviewer
 *  passes it (docs/LOCALIZATION_PROPOSAL.md, "Review and quality").
 */
export const en = {
  "site.title": "Sunshine Ledger",
  "site.description": "Florida state and local legislation, in plain language, mapped by impact.",
  "brand.name": "Sunshine Ledger",
  "brand.badge": "FLORIDA · MVP",

  "nav.browse": "Browse",
  "nav.sponsors": "Sponsors",
  "nav.map": "Map",

  "footer.about":
    "Bernal Labs · Sunshine Ledger MVP. Bill data from LegiScan (Florida) and each city's own legislative records system. Every claim links to a source. Informational only, not legal advice.",
  "footer.how": "How this works",
  "footer.corrections": "Corrections",
  "footer.rss": "RSS",
  "footer.privacy": "Privacy & Terms",
  "footer.security": "Security",

  "freshness.link": "About our data",
  "freshness.failed":
    "We couldn't check how recently the data was updated, so these bills may be out of date · {link}",
  "freshness.stale": "Not updated on schedule: {sources}. Some bills may be out of date · {link}",
  "freshness.neverChecked":
    "At least one source has no recorded update yet, so some bills may be missing or out of date · {link}",
  "freshness.ok": "State and local bills are checked nightly · last checked {date} · {link}",
  "freshness.never": "never",

  "sources.unavailable": "Source status is unavailable right now.",
  "sources.loading": "Loading source status…",
  "sources.schedule": " · {schedule} · last checked {date}",
  "sources.notOnSchedule": " · not updated on schedule",
  "sources.bills.one": "{count} bill",
  "sources.bills.other": "{count} bills",
  "sources.withText": ", {count} with full text",

  "coverage.partial": "Coverage is partial.",
  "coverage.rest":
    "Florida state bills plus {local}; the list below says which. A bill not appearing here does not mean it does not exist.",
  "coverage.localUnknown": "a growing set of local governments",
  "coverage.local.one": "{count} local government",
  "coverage.local.other": "{count} local governments",

  "election.title": "{state} {year} election calendar",
  "election.next": "Next: {label} — {date} {when}",
  "election.today": "(today)",
  "election.inDays.one": "(in {count} day)",
  "election.inDays.other": "(in {count} days)",
  "election.complete":
    "The {year} calendar is complete. Dates for the next election will be added when the state publishes them.",
  "election.alsoOn": "· {label} {date}",
  "election.source":
    "Dates published by the {source}. Shown as civic context only — Sunshine Ledger does not link bills to candidates, parties, or races, and makes no claim about how any bill bears on an election.",

  "card.defaultJurisdiction": "Florida",
  "card.noSummary": "No plain-language summary generated yet.",
  "card.readOriginalText": "Read the original bill text",
  "card.sponsoredBy": "Sponsored by {name}",
  "card.viewOriginal": "View original bill ↗",
  "card.hideSources": "Hide sources",
  "card.showSources": "Sources ({count})",
  "card.flag": "Flag this",
  "card.lastAction": "Last action {date}",
  "card.loadingSources": "Loading sources…",
  "card.whoItAffects": "Who it affects: ",
  "card.sponsors": "Sponsors: ",
  "card.coSponsor": "{name} (co-sponsor)",
  "card.retrieved": " — retrieved {date}",
  "card.aiNote.oneSource":
    "Plain-language summaries above were written by an AI model ({models}) from the source listed here, and are published without a human reviewing each one. They can be wrong or incomplete — the linked source is the authority. Something look off? {flag}.",
  "card.aiNote.manySources":
    "Plain-language summaries above were written by an AI model ({models}) from the sources listed here, and are published without a human reviewing each one. They can be wrong or incomplete — the linked source is the authority. Something look off? {flag}.",
  "card.flagIt": "Flag it",
  "card.noSources":
    "No summary sources yet (no plain-language summary has been generated for this bill) — see \"View original bill\" above for where this data came from.",
  "card.news.title": "Recent news mentions",
  "card.news.unknownOutlet": "unknown outlet",
  "card.news.withDate": "— {publisher}, {date}",
  "card.news.noDate": "— {publisher}",

  "sponsored.none": "No tracked bills for this sponsor.",
  "sponsored.title": "Sponsored and co-sponsored bills",
  "sponsored.titleTagged": "Sponsored and co-sponsored bills tagged {topic}",
  "sponsored.count": " ({count})",
  "sponsored.noneTagged": "None of this sponsor's bills are tagged {topic}.",
  "sponsored.role.sponsor": "sponsor",
  "sponsored.role.coSponsor": "co-sponsor",
  "sponsored.lastAction": " · last action {date}",
  "sponsored.noSummary": "No summary generated yet.",
  "sponsored.showFirst": "Show the first {count}",
  "sponsored.showAll": "Show all {count}",

  "map.viewLabel": "Map view",
  "map.mode.impact": "Impact by county",
  "map.mode.impact.caption":
    "Counties shaded by how many tracked bills apply to them. Click a county to see its bills.",
  "map.mode.sponsorship": "Sponsorship by district",
  "map.mode.sponsorship.caption":
    "State legislative districts shaded by how many tracked bills that district's legislator filed. This measures who introduces legislation, not who it affects — most state bills apply statewide.",
  "map.loading": "Loading map…",
  "map.error.county": "Failed to load map data",
  "map.error.district": "Failed to load district data",
  "map.error.hint":
    "{error} — make sure the backend is running and boundaries are loaded ({loader} or via {seed}).",
  "map.tooltip.county.one": "{name}: {count} bill",
  "map.tooltip.county.other": "{name}: {count} bills",
  "map.tooltip.noSponsor": "no tracked sponsor",
  "map.tooltip.district.one": "{chamber} {name} — {who}: sponsored {count} tracked bill",
  "map.tooltip.district.other": "{chamber} {name} — {who}: sponsored {count} tracked bills",
  "map.tooltip.clickHint": " (click to see their bills)",

  "browse.title": "Tracked bills",
  "browse.intro": "Plain-language summaries of Florida state and local legislation. Every summary links to its source.",
  "browse.filteredGeo": "Filtered to {geo}.",
  "browse.filteredSponsor": "Filtered to bills sponsored by {name}.",
  "browse.thisLegislator": "this legislator",
  "browse.autoDetected": "Showing {place} bills based on your location.",
  "browse.florida": "Florida",
  "browse.viewAll": "View all jurisdictions",
  "browse.search.label": "Search bill number or title",
  "browse.search.placeholder": "Search bill number or title…",
  "browse.filter.jurisdiction": "Filter by jurisdiction",
  "browse.filter.status": "Filter by status",
  "browse.filter.session": "Filter by session",
  "browse.filter.topic": "Filter by topic",
  "browse.all.statuses": "All statuses",
  "browse.all.sessions": "All sessions",
  "browse.all.topics": "All topics",
  "browse.option": "{label} ({count})",
  "browse.error.title": "We couldn't load bills right now.",
  "browse.error.body":
    "The bill service may be restarting or briefly unavailable. Your filters are kept in the address bar, so you can retry or come back to this link.",
  "browse.error.fallback": "Failed to load bills.",
  "browse.retry": "Try again",
  "browse.loading": "Loading bills…",
  "browse.loadingPage": "Loading…",
  "browse.empty": "No bills match your filters.",
  "browse.total.one": "{count} bill",
  "browse.total.other": "{count} bills",
  "browse.pageSuffix": " — page {page} of {pages}",
  "browse.previous": "← Previous",
  "browse.next": "Next →",
  "browse.pageOf": "Page {page} of {pages}",

  "bill.meta.notFound": "Bill not found — {site}",
  "bill.meta.title": "{number} — {place} | {site}",
  "bill.back": "← All bills",
  "bill.untitled": "Untitled item",
  "bill.defaultCity": "the city",
  "bill.agendaNotice":
    "A record from {place}'s agenda{type}, not legislation: it has no bill text, recorded votes or amendments.",
  "bill.status": "Status: ",
  "bill.effective.note": " (per the bill text)",
  "bill.effective.noteSections": " (per the bill text; some sections have their own dates)",
  "bill.provisionDates.one": "{count} provision has its own date",
  "bill.provisionDates.other": "{count} provisions have their own date",
  "bill.whatItDoes": "What it does",
  "bill.aboutItem": "About this item",
  "bill.agendaSummaryNote": "AI summary of the agenda listing. It may call this a bill; it isn't one.",
  "bill.whoItAffects": "Who it affects",
  "bill.sponsors": "Sponsors",
  "bill.coSponsor": " (co-sponsor)",
  "bill.committeeSponsors": "Committee sponsors: ",
  "bill.committeeNote":
    "The committees that produced this version of the bill (a committee substitute). A committee sponsoring a bill is not a legislator's endorsement.",
  "bill.votes": "Votes",
  "bill.votes.noneState": "No recorded roll-call votes for this bill in LegiScan's record.",
  "bill.votes.noneCity": "Roll-call votes aren't collected for city legislation yet.",
  "bill.votes.note":
    "Plain vote tallies from official roll calls — not a score, and not a claim about any legislator.",
  "bill.votes.passed": "Passed {yea}-{nay}",
  "bill.votes.failed": "Failed {yea}-{nay}",
  "bill.votes.notVoting": ", {count} not voting",
  "bill.votes.absent": ", {count} absent",
  "bill.votes.individual.one": "{count} individual vote",
  "bill.votes.individual.other": "{count} individual votes",
  "bill.votes.viewRollCall": "View roll call ↗",
  "bill.amendments": "Amendment history",
  "bill.amendments.noneState": "No amendments recorded for this bill in LegiScan's record.",
  "bill.amendments.noneCity": "Amendments aren't collected for city legislation yet.",
  "bill.amendment.default": "Amendment",
  "bill.amendment.filed": "{label} filed {date}",
  "bill.amendment.inChamber": " in {chamber}",
  "bill.amendment.offeredBy": ", offered by {sponsor}",
  "bill.amendment.adopted": " — adopted",
  "bill.amendment.notAdopted": " — not adopted",
  "bill.amendment.description": " — {description}",
  "bill.amendment.lastAction": " · last action: {action}",
  "bill.report": "Report a problem with this bill",
  "bill.sources": "Sources",
  "bill.sources.retrieved": " — retrieved {date}",
  "bill.news": "Recent news mentions",
  "bill.news.note": "Matched by keyword, unscored — their presence is not a claim about the bill.",
  "bill.news.unknownOutlet": "unknown outlet",
  "bill.aiNote":
    "The plain-language summaries above were written by an AI model ({models}) from the sources listed here, and are published without a human reviewing each one. They can be wrong or incomplete — the linked source is the authority. See {link}.",
  "bill.aiNote.link": "how this works",
  "bill.fullText": "Full bill text",
  "bill.readOriginal": "Read the original bill ↗",
  "bill.miamiNoText":
    "Full text isn't available for Miami items: the city's portal doesn't publish it in a form we can collect.",
  "bill.source.line": "Source: {label} · last checked {date}",
  "bill.source.stale": " · may be out of date",
  "bill.source.tail": " · {link}",
  "bill.source.aboutData": "About our data",

  "map.page.title": "Maps",
  "map.page.intro":
    "Two different views of the same bills: where they apply, and who files them. County and district boundaries only — no per-address mapping at MVP.",

  "challenge.category.factually_wrong.label": "Factually wrong",
  "challenge.category.misleading.label": "Misleading or missing context",
  "challenge.category.wrong_source.label": "Wrong source or quote",
  "challenge.category.outdated.label": "Outdated",
  "challenge.category.wrong_entity.label": "Wrong person or organization",
  "challenge.category.other.label": "Other",
  "challenge.sent":
    "Thanks. A person will review this. If it holds up, the statement is marked “Disputed” while it's checked, and any correction is published with what changed and why.",
  "challenge.kind": "What kind of problem?",
  "challenge.what": "What is wrong?",
  "challenge.whatPlaceholder": "e.g. it says 15 days, but Section 1 of the bill says 30",
  "challenge.evidenceUrl": "Evidence link (optional; reports with evidence are reviewed first)",
  "challenge.evidenceText": "Or quote the evidence (optional)",
  "challenge.named": "I'm named in this record (we'll contact you about a published response)",
  "challenge.email": "Email (optional, if you want a reply; deleted 90 days after the report is resolved)",
  "challenge.error": "Couldn't submit. Try again.",
  "challenge.sending": "Sending…",
  "challenge.submit": "Submit report",
  "challenge.cancel": "Cancel",
} as const;

export type MessageKey = keyof typeof en;
