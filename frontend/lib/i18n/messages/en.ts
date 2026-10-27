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
} as const;

export type MessageKey = keyof typeof en;
