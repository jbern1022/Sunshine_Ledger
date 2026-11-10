import { describe, it, expect } from "vitest";
import { cleanAnswers, matchBill } from "./impactLens";
import type { Criteria, CriterionTest, LensBill, LensEntry } from "./impactLens";

// Slice 3 of docs/IMPACT_LENS_ROLE_LOCATIONS.md: several roles. Each entry is evaluated once
// per role, with that role's location kind; it holds if any role holds, and is ruled out only
// if every role rules it out.

const crit = (over: Partial<Criteria>): Criteria => ({
  entry_index: 0, vocabulary_version: 2, relevance: "direct", audience: null, affected: null,
  requires: [], excludes: [], unmapped: [], ambiguous: null, ...over,
});
const role = (...r: string[]) => ({ kind: "attr" as const, attr: "role" as const, any_of: r });
const inCounty = (c: string): CriterionTest => ({ attr: "jurisdiction", op: "in", values: [`county:${c}`], from: { kind: "condition", index: 0 } });
const entry = (audience: string, county: string): LensEntry => ({
  group: audience, text: "t", quote: "q", conditions: [{ text: `in ${county}`, quote: "q" }], exceptions: [],
  criteria: crit({ audience: role(audience), requires: [inCounty(county)] }), reviewed: false,
} as LensEntry);
const bill = (...entries: LensEntry[]): LensBill => ({
  complete: true, entries,
  role_locations: { landlord: "property", employer: "business", renter: "residence" },
});
const run = (b: LensBill, a: Parameters<typeof matchBill>[1]) => matchBill(b, a);

describe("several roles", () => {
  it("a landlord who is also an employer is matched by the employer rule at the business location", () => {
    const b = bill(entry("employer", "Orange"));
    // As a landlord alone the property county is irrelevant to this rule: the role does not match.
    expect(run(b, { role: "landlord", property_county: "Duval" }).result).toBe("does_not_appear");
    expect(run(b, { role: ["landlord", "employer"], property_county: "Duval", business_county: "Orange" }).result).toBe("applies");
  });

  it("each role uses its own location: a Duval business does not satisfy a rental rule for Orange", () => {
    const b = bill(entry("landlord", "Orange"));
    expect(run(b, { role: ["landlord", "employer"], property_county: "Duval", business_county: "Orange" }).result).toBe("does_not_appear");
    expect(run(b, { role: ["landlord", "employer"], property_county: "Orange", business_county: "Duval" }).result).toBe("applies");
  });

  it("is ruled out only when every role rules it out", () => {
    const b = bill(entry("landlord", "Orange"), entry("employer", "Orange"));
    expect(run(b, { role: ["landlord", "employer"], property_county: "Leon", business_county: "Leon" }).result).toBe("does_not_appear");
  });

  it("asks only for a location a still-open role needs, and not for roles already settled", () => {
    const b = bill(entry("landlord", "Orange"), entry("employer", "Orange"));
    const r = run(b, { role: ["landlord", "employer"], property_county: "Leon" });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual(["business_county"]);
  });

  it("a list of one role behaves exactly like the plain role", () => {
    const b = bill(entry("landlord", "Orange"));
    const a = { property_county: "Orange" };
    expect(run(b, { ...a, role: ["landlord"] }).result).toBe(run(b, { ...a, role: "landlord" }).result);
  });

  it("stored answers keep a role list, de-duplicated, and collapse a single role", () => {
    expect(cleanAnswers({ role: ["landlord", "employer", "landlord"] }).role).toEqual(["landlord", "employer"]);
    expect(cleanAnswers({ role: ["landlord"] }).role).toBe("landlord");
  });
});
