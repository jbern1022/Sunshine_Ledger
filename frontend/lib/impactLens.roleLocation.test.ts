import { describe, it, expect } from "vitest";
import { matchBill } from "./impactLens";
import type { Criteria, CriterionTest, LensBill, LensEntry } from "./impactLens";

// Slice 1 of docs/IMPACT_LENS_ROLE_LOCATIONS.md: a place a bill names is
// compared with the reader's location of the kind the entry's bound role
// regulates (residence, property or business), not always with where they live.

const crit = (over: Partial<Criteria>): Criteria => ({
  entry_index: 0, vocabulary_version: 2, relevance: "direct", audience: null, affected: null,
  requires: [], excludes: [], unmapped: [], ambiguous: null, ...over,
});
const role = (...r: string[]) => ({ kind: "attr" as const, attr: "role" as const, any_of: r });
const inCounty = (...c: string[]): CriterionTest => ({
  attr: "jurisdiction", op: "in", values: c.map((x) => `county:${x}`), from: { kind: "condition", index: 0 },
});
// The role-to-location table the server sends with every bill.
const ROLE_LOCATIONS = {
  renter: "residence", insured: "residence", local_government: "residence",
  landlord: "property", homeowner: "property", property_developer: "property",
  employer: "business", business_owner: "business", employee: "business", healthcare_provider: "business",
} as const;
const bill = (audience: string, ...counties: string[]): LensBill => ({
  complete: true,
  role_locations: ROLE_LOCATIONS,
  entries: [{
    group: audience, text: "t", quote: "q", conditions: [{ text: `in ${counties.join(", ")}`, quote: "q" }], exceptions: [],
    criteria: crit({ audience: role(audience), requires: [inCounty(...counties)] }), reviewed: false,
  } as LensEntry],
});
const result = (b: LensBill, a: Parameters<typeof matchBill>[1]) => matchBill(b, a).result;

describe("a place the bill names is compared with the location the role regulates", () => {
  it("a Miami-Dade resident with a Broward rental property is matched by a Broward landlord rule", () => {
    expect(
      result(bill("landlord", "Broward"), { role: "landlord", county: "Miami-Dade", property_county: "Broward" }),
    ).toBe("applies");
  });

  it("the same landlord whose property is in Palm Beach is not matched by the Broward rule", () => {
    expect(
      result(bill("landlord", "Broward"), { role: "landlord", county: "Broward", property_county: "Palm Beach" }),
    ).toBe("does_not_appear");
  });

  it("without a property county it asks for the property county, never the residence county", () => {
    const r = matchBill(bill("landlord", "Broward"), { role: "landlord", county: "Miami-Dade" });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual(["property_county"]);
  });

  it("a renter is still compared by where they live, even with a property answer present", () => {
    const b = bill("renter", "Broward");
    expect(result(b, { role: "renter", county: "Miami-Dade", property_county: "Broward" })).toBe("does_not_appear");
    expect(result(b, { role: "renter", county: "Broward" })).toBe("applies");
  });

  it("an employee is compared by where they work, not where they live", () => {
    const b = bill("employee", "Orange");
    expect(result(b, { role: "employee", county: "Duval", business_county: "Orange" })).toBe("applies");
    expect(result(b, { role: "employee", county: "Orange", business_county: "Duval" })).toBe("does_not_appear");
    expect(matchBill(b, { role: "employee", county: "Orange" }).ask).toEqual(["business_county"]);
  });

  it("a city named by the rule is compared with the property's city, and asked for only when needed", () => {
    const b: LensBill = {
      complete: true,
      role_locations: ROLE_LOCATIONS,
      entries: [{
        group: "landlord", text: "t", quote: "q", conditions: [{ text: "in Miami", quote: "q" }], exceptions: [],
        criteria: crit({
          audience: role("landlord"),
          requires: [{ attr: "jurisdiction", op: "in", values: ["municipality:Miami"], from: { kind: "condition", index: 0 } }],
        }),
        reviewed: false,
      } as LensEntry],
    };
    expect(result(b, { role: "landlord", property_county: "Miami-Dade", property_municipality: "Miami" })).toBe("applies");
    expect(result(b, { role: "landlord", municipality: "Miami", property_county: "Miami-Dade" })).toBe("cant_determine");
    expect(matchBill(b, { role: "landlord", property_county: "Miami-Dade" }).ask).toEqual(["property_municipality"]);
  });

  it("without the server's table every place is compared with residence, as before", () => {
    const b = { ...bill("landlord", "Broward"), role_locations: undefined };
    expect(result(b, { role: "landlord", county: "Miami-Dade", property_county: "Broward" })).toBe("does_not_appear");
  });

  it("an 'anyone' provision or an unlisted role keeps comparing with residence", () => {
    const anyone: LensBill = {
      complete: true,
      role_locations: ROLE_LOCATIONS,
      entries: [{
        group: "Anyone", text: "t", quote: "q", conditions: [{ text: "in Broward", quote: "q" }], exceptions: [],
        criteria: crit({ audience: { kind: "anyone" }, requires: [inCounty("Broward")] }), reviewed: false,
      } as LensEntry],
    };
    expect(matchBill(anyone, { role: "landlord", county: "Broward", property_county: "Duval" }).result).toBe("everyone_only");
    expect(result(bill("some_new_role", "Broward"), { role: "some_new_role", county: "Broward" })).toBe("applies");
  });
});
