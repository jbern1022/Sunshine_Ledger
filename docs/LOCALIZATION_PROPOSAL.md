# Spanish and Haitian Creole: options and a recommendation

Status: proposal for Joe's review, 2026-10-26. Nothing is built and the scope is not
decided (Todoist `6hr2G4QM4qWWJGPG`). Related: Pajarito i18n `6hgq7CVq3M5p9jFq`
(English, Spanish, Haitian Creole; "review translations before release"), Navigator
multilingual requirements `6hgqqQMrhFJfgwjv`.

This proposal makes no claim that any translation exists or has been reviewed.

## Where the app stands

- Next.js 16 App Router, React 19; `<html lang="en">` is hard-coded in
  `frontend/app/layout.tsx`. No i18n library, no message catalogue.
- User-facing English is inline in about 40 components and pages. The pages also build
  sentences from data (plurals, dates, counts, "page X of Y").
- Generated content is stored in English: bill summaries (`claims`), bill layers
  (`bill_layers.items`), Who it affects entries, Impact Lens question wording (partly
  in the backend: `vocabulary.py`, `api/impact_lens.py`), correction explanations.
- Source material (bill text, staff analyses, agendas) is in English and will stay.
- The homepage is steered by IP location in `proxy.ts` (a cookie, once per visit).
- Dates, numbers and pluralization are hand-formatted in several places.

## Three kinds of text, three answers

| Kind | Examples | Approach |
|---|---|---|
| Interface | navigation, labels, errors, empty states, privacy and methodology pages | a message catalogue per locale, reviewed by fluent speakers |
| Generated, per bill | summaries, interpretations, Who it affects, Expected Effect | translated at generation time or on demand; always labelled as a translation of an English original |
| Source material | bill text, amendments, agendas | stays in the original language; link and label, do not translate |

## Decisions

### 1. Library

- **next-intl** (recommended): built for the App Router, server and client components,
  ICU plurals, date and number formatting, typed message keys, and works with a locale
  path segment. Widely used.
- Alternatives: `react-intl` (more manual with the App Router), `i18next` (flexible, more
  setup), or a home-made dictionary (cheapest now, loses ICU plurals and formatting).

### 2. URL strategy

- **Locale prefix, `/es/...` and `/ht/...`, English at `/` (recommended).** Shareable,
  crawlable, `hreflang` works, lets the RSS, sitemap and share links carry a language.
  Costs a `[locale]` segment on every route and a rewrite of internal links.
- Cookie only: simplest URLs, but a link does not carry the language and search engines
  see one version.
- Subdomains: heavier to run, no benefit at this size.

Use ISO codes `es` and `ht` (Haitian Creole is `ht`). Treat Haitian Creole as its own
language with its own reviewer and its own user tests, not a variant of Spanish or French.

### 3. Interaction with the IP-based homepage

Location and language are separate. The IP lookup should choose a jurisdiction and
never a language. Language comes from, in order: the URL prefix, a stored choice, the
browser `Accept-Language`, then English. A visible language switch on every page. The
`sl_geo_resolved` cookie stays as it is; a language cookie would be a second cookie and
needs a line on the privacy page, which today says it sets one cookie only. Using the
URL prefix alone avoids that.

### 4. Generated content: when to translate

- **A. At generation time** (store `lang` on each layer and claim). Fastest to read,
  costs an LLM pass per language per bill version (about 2 more passes for roughly 6,000
  bills, and again at each re-summary), and needs a new column plus a check that every
  translation matches its English version.
- **B. On demand, cached.** Translate when a reader first opens a bill in that language;
  cache by (object, version, lang). Cheaper, first reader waits, and the translation
  quality is not reviewed before it is shown.
- **C. Interface only at first; bills stay English with a notice.** Fastest to ship and
  honest, but the content readers came for is not in their language.

Recommended: C first, then A for a **small reviewed set** (the most-viewed bills and
the Impact Lens questions), with B only after a reviewer has checked a sample from the
same model. Whatever is shown must say so: "Translated from the English summary by an
AI; the English version is the reference," and the English original one click away. A
correction to the English version must mark the translation stale.

Risk: legal and civic terms ("preemption", "ad valorem", "appropriation") translate
badly without a glossary, and an LLM translation of a summary of a bill is two steps from
the source. The existing "AI-generated, not reviewed by a person" labelling has to carry
into every language.

### 5. Review and quality

- A glossary of civic and legal terms per language, approved by a fluent reviewer before
  any UI string ships.
- Spanish and Haitian Creole each get a named fluent reviewer and a small user test.
- Releases are gated per language: English ships alone until a language passes review.
  The language switch lists only languages that passed.
- No machine translation is shipped as reviewed.

### 6. Other work this touches

- Dates, numbers, plurals, accessibility labels, and the lens answers (stored in
  `sessionStorage`) need locale-aware formatting.
- The Impact Lens question wording moves from the backend into the catalogue, or the API
  returns keys.
- Emails and alerts (not built) need per-locale templates.
- RSS: separate feeds per language, or none until bills are translated.
- Right-to-left is not needed for these languages.
- `Accept-Language` negotiation must not change a URL the reader chose.

## Proposed sequence

1. Decide URL strategy and library (this document).
2. Extract strings behind a catalogue in English only, with no visible change, behind
   the ESLint rule "no literal user-facing strings" from `6hgq7CVq3M5p9jFq`.
3. Add the locale segment and language switch with English only.
4. Glossary and reviewer for Spanish, then interface strings, then release Spanish.
5. Repeat for Haitian Creole with its own reviewer.
6. Generated content: a reviewed pilot set, then decide A or B from review results.

Steps 2 and 3 are code I can do without your input once the URL decision is made. Steps
4 and 5 are blocked on reviewers.

## What I need from you

- URL strategy and library (recommended above).
- Whether bill content is in scope for the first release or interface only.
- Who the Spanish and Haitian Creole reviewers are.
