import { describe, it, expect } from "vitest";
import { cleanAnswers, matchBill, placesOf } from "./impactLens";
import type { Criteria, CriterionTest, LensBill, LensEntry } from "./impactLens";

// Slice 2 of docs/IMPACT_LENS_ROLE_LOCATIONS.md: several places of one kind.
// A place the bill names matches if ANY of the reader's places of that kind matches.

const crit = (over: Partial<Criteria>): Criteria => ({
  entry_index: 0, vocabulary_version: 2, relevance: "direct", audience: null, affected: null,
  requires: [], excludes: [], unmapped: [], ambiguous: null, ...over,
});
const role = (...r: string[]) => ({ kind: "attr" as const, attr: "role" as const, any_of: r });
const test = (op: "in" | "not_in", ...c: string[]): CriterionTest => ({
  attr: "jurisdiction", op, values: c.map((x) => `county:${x}`), from: { kind: "condition", index: 0 },
});
const bill = (requires: CriterionTest[], excludes: CriterionTest[] = []): LensBill => ({
  complete: true,
  role_locations: { landlord: "property", renter: "residence" },
  entries: [{
    group: "landlord", text: "t", quote: "q", conditions: [{ text: "c", quote: "q" }], exceptions: [],
    criteria: crit({ audience: role("landlord"), requires, excludes }), reviewed: false,
  } as LensEntry],
});
const result = (b: LensBill, a: Parameters<typeof matchBill>[1]) => matchBill(b, a).result;

describe("several places of one kind", () => {
  it("a landlord with rentals in Leon and Duval is matched by a Duval rule", () => {
    expect(result(bill([test("in", "Duval")]), { role: "landlord", property_county: ["Leon", "Duval"] })).toBe("applies");
  });

  it("is ruled out only when every listed place is ruled out", () => {
    expect(result(bill([test("in", "Duval")]), { role: "landlord", property_county: ["Leon", "Orange"] })).toBe("does_not_appear");
  });

  it("an exclusion on one listed place does not rule the reader out if another place is outside it", () => {
    // not_in Duval: holds when the place is not Duval. Leon is not Duval.
    expect(result(bill([], [test("in", "Duval")]), { role: "landlord", property_county: ["Duval", "Leon"] })).toBe("applies");
  });

  it("a one-item list behaves exactly like the plain string", () => {
    const b = bill([test("in", "Duval")]);
    expect(result(b, { role: "landlord", property_county: ["Duval"] })).toBe(result(b, { role: "landlord", property_county: "Duval" }));
  });

  it("an empty list counts as unanswered and asks for the county", () => {
    const r = matchBill(bill([test("in", "Duval")]), { role: "landlord", property_county: [] });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual(["property_county"]);
  });
});

describe("stored answers", () => {
  it("keeps a list for a place key, de-duplicated, and collapses a single name to a string", () => {
    expect(cleanAnswers({ property_county: ["Leon", "Leon", "Duval", ""] }).property_county).toEqual(["Leon", "Duval"]);
    expect(cleanAnswers({ property_county: ["Leon", "Leon"] }).property_county).toBe("Leon");
  });

  it("caps a list and ignores lists on keys that take one value", () => {
    const many = Array.from({ length: 30 }, (_, i) => `County${i}`);
    expect(placesOf(cleanAnswers({ county: many }).county)).toHaveLength(10);
    expect(cleanAnswers({ role: ["landlord"], property_type: ["x"] })).toEqual({});
    expect(cleanAnswers({ county: [1, null, "Duval"] }).county).toBe("Duval");
  });
});
