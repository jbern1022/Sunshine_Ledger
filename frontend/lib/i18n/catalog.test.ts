import { describe, it, expect } from "vitest";

import { en } from "./messages/en";

// Every language added to LOCALES must have its catalogue listed here. A
// catalogue passes only if it defines exactly the English keys, with the same
// {placeholders} in each message, so a translation can't silently drop a
// number, a link or a date.
import { LOCALES } from "./index";
const CATALOGS: Record<string, Record<string, string>> = { en };

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("message catalogues", () => {
  it("lists a catalogue for every shipped locale", () => {
    for (const locale of LOCALES) expect(CATALOGS[locale], `catalogue for ${locale}`).toBeDefined();
  });

  for (const locale of Object.keys(CATALOGS).filter((l) => l !== "en")) {
    it(`${locale} defines the English keys and placeholders, and nothing else`, () => {
      const catalog = CATALOGS[locale];
      expect(Object.keys(catalog).sort()).toEqual(Object.keys(en).sort());
      for (const [key, message] of Object.entries(catalog)) {
        expect(placeholders(message), key).toEqual(placeholders((en as Record<string, string>)[key]));
      }
    });
  }

  it("English plural keys come as a complete .one/.other pair", () => {
    const bases = new Set(Object.keys(en).filter((k) => /\.(one|other)$/.test(k)).map((k) => k.replace(/\.(one|other)$/, "")));
    for (const base of bases) {
      expect(en, `${base}.one`).toHaveProperty([`${base}.one`]);
      expect(en, `${base}.other`).toHaveProperty([`${base}.other`]);
    }
  });

  it("uses no message that is empty", () => {
    for (const [key, message] of Object.entries(en)) expect(message.trim().length, key).toBeGreaterThan(0);
  });
});
