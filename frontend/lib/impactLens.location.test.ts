import { describe, it, expect } from "vitest";
import { matchBill } from "./impactLens";
import type { Criteria, CriterionTest, LensBill, LensEntry } from "./impactLens";

// Pins what the matcher does today with ONE location answer, for the scenarios
// in docs/IMPACT_LENS_LOCATION_SEMANTICS.md. Cases marked LIMITATION are
// behaviour the document proposes to change; if a test here starts failing
// because the model changed on purpose, update the document with it.

const crit = (over: Partial<Criteria>): Criteria => ({
  entry_index: 0, vocabulary_version: 2, relevance: "direct", audience: null, affected: null,
  requires: [], excludes: [], unmapped: [], ambiguous: null, ...over,
});
const role = (...r: string[]) => ({ kind: "attr" as const, attr: "role" as const, any_of: r });
const inCounty = (...c: string[]): CriterionTest => ({
  attr: "jurisdiction", op: "in", values: c.map((x) => `county:${x}`), from: { kind: "condition", index: 0 },
});
const bill = (audience: string, ...counties: string[]): LensBill => ({
  complete: true,
  entries: [{
    group: audience, text: "t", quote: "q", conditions: [{ text: `in ${counties.join(", ")}`, quote: "q" }], exceptions: [],
    criteria: crit({ audience: role(audience), requires: [inCounty(...counties)] }), reviewed: false,
  } as LensEntry],
});
const result = (b: LensBill, a: Parameters<typeof matchBill>[1]) => matchBill(b, a).result;

describe("one county answer, whatever the role", () => {
  it("a renter who lives where they rent is matched", () => {
    expect(result(bill("renter", "Duval"), { role: "renter", county: "Duval" })).toBe("applies");
  });

  it("LIMITATION: a landlord living in Leon with a Duval rental gets 'does not appear to apply'", () => {
    expect(result(bill("landlord", "Duval"), { role: "landlord", county: "Leon" })).toBe("does_not_appear");
  });

  it("LIMITATION: an employee's home county, not their workplace, decides", () => {
    expect(result(bill("employee", "Miami-Dade"), { role: "employee", county: "Duval" })).toBe("does_not_appear");
  });

  it("LIMITATION: the answer cannot hold two places, so a two-home owner is matched on one", () => {
    const b = bill("homeowner", "Leon");
    expect(result(b, { role: "homeowner", county: "Duval" })).toBe("does_not_appear");
    expect(result(b, { role: "homeowner", county: "Leon" })).toBe("applies");
  });

  it("without a county the lens asks for it rather than guessing", () => {
    const r = matchBill(bill("landlord", "Duval"), { role: "landlord" });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual(["county"]);
  });

  it("a local government is still asked for a county, since the model has no 'government's own area'", () => {
    const r = matchBill(bill("local_government", "Duval"), { role: "local_government" });
    expect(r.ask).toEqual(["county"]);
  });
});
