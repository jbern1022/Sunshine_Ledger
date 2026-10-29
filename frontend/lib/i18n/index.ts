import { createElement, Fragment, type ReactNode } from "react";

import { en, type MessageKey } from "./messages/en";

export type { MessageKey };

/** Languages the site ships. A language is added here only after its catalogue
 *  has passed fluent-speaker review (docs/LOCALIZATION_PROPOSAL.md). */
export const LOCALES = ["en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";

type Catalog = Record<MessageKey, string>;
const CATALOGS: Record<Locale, Catalog> = { en };

/** BCP 47 tag for Intl formatting. Haitian Creole will be "ht", not a variant of French. */
const INTL_TAG: Record<Locale, string> = { en: "en-US" };

export function intlTag(locale: Locale = DEFAULT_LOCALE): string {
  return INTL_TAG[locale];
}

export type Params = Record<string, string | number>;

const PLACEHOLDER = /\{(\w+)\}/g;

/** The message for `key`, with `{name}` replaced from `params`. A plural key
 *  (`<key>.one`, `<key>.other`, ...) is chosen by `params.count`. A language
 *  missing a key falls back to English, never to a blank. */
export function translate(locale: Locale, key: string, params: Params = {}): string {
  const catalog = CATALOGS[locale] as Record<string, string>;
  const fallback = CATALOGS[DEFAULT_LOCALE] as Record<string, string>;
  const pick = (name: string) => catalog[name] ?? fallback[name];

  let template = pick(key);
  if (template === undefined && typeof params.count === "number") {
    const category = new Intl.PluralRules(intlTag(locale)).select(params.count);
    template = pick(`${key}.${category}`) ?? pick(`${key}.other`);
  }
  if (template === undefined) return key; // visible in the page and caught by the type of `t`
  return template.replace(PLACEHOLDER, (whole, name: string) =>
    name in params ? (typeof params[name] === "number" ? formatNumber(params[name] as number, locale) : String(params[name])) : whole,
  );
}

type PluralBase<K extends string> = K extends `${infer B}.${"zero" | "one" | "two" | "few" | "many" | "other"}` ? B : never;
/** Every key a caller may pass: a full key, or the base of a plural. */
export type TranslationKey = MessageKey | PluralBase<MessageKey>;

export function t(key: TranslationKey, params?: Params, locale: Locale = DEFAULT_LOCALE): string {
  return translate(locale, key, params);
}

/** Like `t`, but a parameter may be a React node (a link inside a sentence).
 *  Returns the pieces in order as one fragment, so callers need no keys. */
export function tRich(key: TranslationKey, parts: Record<string, ReactNode>, locale: Locale = DEFAULT_LOCALE): ReactNode {
  const text = translate(locale, key, {});
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(PLACEHOLDER)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(m[1] in parts ? parts[m[1]] : m[0]);
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return createElement(Fragment, null, ...out);
}

export function formatNumber(n: number, locale: Locale = DEFAULT_LOCALE): string {
  return n.toLocaleString(intlTag(locale));
}
