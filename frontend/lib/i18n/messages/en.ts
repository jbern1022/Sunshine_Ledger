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
} as const;

export type MessageKey = keyof typeof en;
