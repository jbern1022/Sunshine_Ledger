import { describe, it, expect } from "vitest";
import { matchBill, evaluateEntry, RESULT_LABEL } from "./impactLens";
import type { Criteria, CriterionTest, LensBill, LensEntry } from "./impactLens";

const COVERED = ["county:Duval", "county:Miami-Dade"];

const crit = (over: Partial<Criteria> = {}): Criteria => ({
  entry_index: 0,
  vocabulary_version: 2,
  relevance: "direct",
  audience: null,
  affected: null,
  requires: [],
  excludes: [],
  unmapped: [],
  ambiguous: null,
  ...over,
});

const role = (...r: string[]) => ({ kind: "attr" as const, attr: "role" as const, any_of: r });
const req = (attr: string, values: string[], index = 0): CriterionTest => ({ attr, op: "in", values, from: { kind: "condition", index } });
const exc = (attr: string, values: string[], index = 0): CriterionTest => ({ attr, op: "in", values, from: { kind: "exception", index } });

const entry = (group: string, criteria: Criteria | null, over: Partial<LensEntry> = {}): LensEntry => ({
  group,
  text: `${group} text`,
  quote: `Quote for ${group}.`,
  conditions: [{ text: "Applies in Duval and Miami-Dade.", quote: "q-cond" }],
  exceptions: [{ text: "Not single-family homes.", quote: "q-exc" }],
  criteria,
  reviewed: false,
  ...over,
});

// The prototype's fictional rental bill, now with real criteria shapes.
const E1 = entry("Landlords", crit({ audience: role("landlord"), requires: [req("jurisdiction", COVERED)], excludes: [exc("property_type", ["single_family"])] }));
const E2 = entry("Tenants", crit({ audience: role("renter"), requires: [req("jurisdiction", COVERED)] }));
const E3 = entry("Developers", crit({ audience: role("property_developer"), requires: [req("property_type", ["multifamily"])] }), {
  conditions: [{ text: "A multifamily project.", quote: "q" }],
});
const E4 = entry("Local governments", crit({ audience: role("local_government") }), { conditions: [], exceptions: [] });
const rental: LensBill = { entries: [E1, E2, E3, E4], complete: true };

const label = (bill: LensBill, answers: Parameters<typeof matchBill>[1]) => matchBill(bill, answers).label;

describe("the four core results", () => {
  it("a renter in a covered county: Applies to You, and nothing more to ask", () => {
    const r = matchBill(rental, { role: "renter", county: "Duval" });
    expect(r.result).toBe("applies");
    expect(r.label).toBe("Applies to You");
    expect(r.ask).toEqual([]);
    expect(r.basis[0].entry.group).toBe("Tenants");
    expect(r.why[0].quote).toBe("Quote for Tenants.");
    expect(r.why[0].circumstances).toEqual([{ key: "role", value: "renter" }, { key: "county", value: "Duval" }]);
  });

  it("a renter whose county is unknown: Can't Determine, asking only the county", () => {
    const r = matchBill(rental, { role: "renter" });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual(["county"]);
  });

  it("a renter outside the covered counties: Does Not Appear to Apply (the layer is complete)", () => {
    const r = matchBill(rental, { role: "renter", county: "Orange" });
    expect(r.result).toBe("does_not_appear");
    expect(r.ask).toEqual([]);
    expect(r.why).toEqual([]);
  });

  it("a landlord in a covered county: unknown until the property type, then the exception decides", () => {
    expect(matchBill(rental, { role: "landlord", county: "Miami-Dade" }).ask).toEqual(["property_type"]);
    expect(label(rental, { role: "landlord", county: "Miami-Dade", property_type: "single_family" })).toBe("Does Not Appear to Apply");
    expect(label(rental, { role: "landlord", county: "Miami-Dade", property_type: "multifamily" })).toBe("Applies to You");
  });

  it("a developer is not asked for a county the entry never mentions", () => {
    const r = matchBill(rental, { role: "property_developer" });
    expect(r.ask).toEqual(["property_type"]);
    expect(label(rental, { role: "property_developer", property_type: "multifamily" })).toBe("Applies to You");
  });

  it("with nothing answered, the first question is the role", () => {
    const r = matchBill(rental, {});
    expect(r.result).toBe("cant_determine");
    expect(r.ask[0]).toBe("role");
  });

  it("a role no entry mentions: Does Not Appear to Apply, scoped by the completeness rule", () => {
    expect(label(rental, { role: "homeowner" })).toBe("Does Not Appear to Apply");
  });
});

describe("Does Not Appear to Apply needs a complete Who layer", () => {
  const incomplete: LensBill = { ...rental, complete: false };

  it("an incomplete layer gives Can't Determine instead", () => {
    expect(label(incomplete, { role: "homeowner" })).toBe("Can't Determine");
    expect(label(incomplete, { role: "renter", county: "Orange" })).toBe("Can't Determine");
  });

  it("an incomplete layer still lets a real match through", () => {
    expect(label(incomplete, { role: "renter", county: "Duval" })).toBe("Applies to You");
  });

  it("an unmapped entry keeps the answer at Can't Determine even if the layer is flagged complete", () => {
    const bill: LensBill = { complete: true, entries: [...rental.entries, entry("Farms", null)] };
    expect(label(bill, { role: "homeowner" })).toBe("Can't Determine");
  });

  it("a bill with no entries is Can't Determine", () => {
    expect(label({ entries: [], complete: true }, { role: "renter" })).toBe("Can't Determine");
  });
});

describe("unknown is not no", () => {
  it("an unmapped condition makes a would-be match unknown", () => {
    const e = entry("Landlords", crit({ audience: role("landlord"), unmapped: [{ kind: "condition", index: 0, reason: "a date" }] }));
    const r = matchBill({ entries: [e], complete: true }, { role: "landlord" });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual([]); // a question cannot settle it
  });

  it("an unmapped audience is unknown for every role", () => {
    const e = entry("Courts", crit({ audience: null, unmapped: [{ kind: "audience", index: null, reason: "no role" }] }), { conditions: [], exceptions: [] });
    expect(label({ entries: [e], complete: true }, { role: "renter" })).toBe("Can't Determine");
  });

  it("a known failing requirement rules an entry out even when another condition is unmapped", () => {
    const e = entry("Tenants", crit({ audience: role("renter"), requires: [req("jurisdiction", COVERED)], unmapped: [{ kind: "condition", index: 1, reason: "a date" }] }));
    const r = matchBill({ entries: [e], complete: true }, { role: "renter", county: "Orange" });
    expect(r.result).toBe("does_not_appear");
  });

  it("an unknown requirement attribute this matcher cannot test stays unknown", () => {
    const e = entry("Tenants", crit({ audience: role("renter"), requires: [req("lease_start", ["x"])] }));
    expect(label({ entries: [e], complete: true }, { role: "renter" })).toBe("Can't Determine");
  });
});

describe("the affected party", () => {
  // S1166-shaped: the insurer is bound, an insured is protected.
  const disclose = entry("Each health insurer", crit({ audience: null, affected: role("insured"), unmapped: [{ kind: "audience", index: null, reason: "no insurer role" }] }), { conditions: [], exceptions: [] });
  const physicians = entry("Treating physicians", crit({ audience: role("healthcare_provider") }), { conditions: [], exceptions: [] });
  const bill: LensBill = { entries: [disclose, physicians], complete: true };

  it("an insured reader is an affected party, even though the bound party is unmapped", () => {
    const r = matchBill(bill, { role: "insured" });
    expect(r.result).toBe("applies");
    expect(r.basis[0].relation).toBe("affected");
    expect(r.basis[0].reason).toBe("This provision protects or burdens people like you.");
  });

  it("a physician is the bound party of their entry", () => {
    const r = matchBill(bill, { role: "healthcare_provider" });
    expect(r.result).toBe("applies");
    expect(r.basis[0].relation).toBe("bound");
  });

  it("another role stays unknown: the unmapped insurer entry might be about them", () => {
    expect(label(bill, { role: "renter" })).toBe("Can't Determine");
  });
});

describe("Anyone entries are a separate line, never the headline", () => {
  const discrimination = entry("Anyone", crit({ audience: { kind: "anyone" } }), { conditions: [], exceptions: [] });

  it("they sit beside a person-specific result", () => {
    const r = matchBill({ entries: [E4, discrimination], complete: true }, { role: "local_government" });
    expect(r.result).toBe("applies");
    expect(r.basis.map((e) => e.entry.group)).toEqual(["Local governments"]);
    expect(r.everyone.map((e) => e.entry.group)).toEqual(["Anyone"]);
  });

  it("they never turn a no into Applies to You", () => {
    const r = matchBill({ entries: [E2, discrimination], complete: true }, { role: "renter", county: "Orange" });
    expect(r.result).toBe("does_not_appear");
    expect(r.everyone).toHaveLength(1);
  });

  it("a bill with only Anyone entries headlines Applies to Everyone", () => {
    const r = matchBill({ entries: [discrimination], complete: true }, { role: "renter" });
    expect(r.result).toBe("everyone_only");
    expect(r.label).toBe("Applies to Everyone");
  });

  it("an Anyone entry with an untestable condition is uncertainty, not a miss", () => {
    const risky = entry("Anyone", crit({ audience: { kind: "anyone" }, unmapped: [{ kind: "condition", index: 0, reason: "a date" }] }));
    const r = matchBill({ entries: [E2, risky], complete: true }, { role: "renter", county: "Orange" });
    expect(r.result).toBe("cant_determine");
  });
});

describe("ambiguity has its own state", () => {
  const ambiguous = entry("Counties", crit({ audience: role("local_government"), ambiguous: { question: "Does the setback limit or the height cap control?", quote: "q-amb" } }), { conditions: [], exceptions: [] });

  it("is shown instead of Can't Determine, with the question", () => {
    const r = matchBill({ entries: [ambiguous, E1], complete: true }, { role: "local_government" });
    expect(r.result).toBe("ambiguous");
    expect(r.label).toBe("Text Is Ambiguous Here");
    expect(r.ambiguity?.question).toContain("setback");
  });

  it("is outranked by an unambiguous match", () => {
    const r = matchBill({ entries: [ambiguous, E4], complete: true }, { role: "local_government" });
    expect(r.result).toBe("applies");
  });

  it("an ambiguous entry the reader is ruled out of does not count", () => {
    expect(label({ entries: [ambiguous], complete: true }, { role: "renter" })).toBe("Does Not Appear to Apply");
  });
});

describe("municipalities and counties", () => {
  const city = entry("Landlords", crit({ audience: role("landlord"), requires: [req("jurisdiction", ["municipality:Jacksonville", "county:Miami-Dade"])] }));
  const bill: LensBill = { entries: [city], complete: true };

  it("a county value matches the reader's county", () => {
    expect(label(bill, { role: "landlord", county: "Miami-Dade" })).toBe("Applies to You");
  });

  it("a municipality value is unknown until the reader gives one, then asks for it", () => {
    const r = matchBill(bill, { role: "landlord", county: "Duval" });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual(["municipality"]);
  });

  it("a municipality answer settles it either way", () => {
    expect(label(bill, { role: "landlord", county: "Duval", municipality: "Jacksonville" })).toBe("Applies to You");
    expect(label(bill, { role: "landlord", county: "Duval", municipality: "Neptune Beach" })).toBe("Does Not Appear to Apply");
  });

  it("the county is asked before the municipality", () => {
    expect(matchBill(bill, { role: "landlord" }).ask).toEqual(["county"]);
  });
});

describe("what the answer is based on", () => {
  it("reports whether any entry behind the headline is unreviewed", () => {
    expect(matchBill(rental, { role: "renter", county: "Duval" }).unreviewed).toBe(true);
    const reviewed: LensBill = { complete: true, entries: [{ ...E2, reviewed: true }] };
    expect(matchBill(reviewed, { role: "renter", county: "Duval" }).unreviewed).toBe(false);
  });

  it("an indirect entry gives May Affect You, never Applies", () => {
    const forecast = entry("Tenants", crit({ audience: role("renter"), relevance: "indirect", requires: [req("jurisdiction", COVERED)] }));
    const r = matchBill({ entries: [forecast], complete: true }, { role: "renter", county: "Duval" });
    expect(r.result).toBe("may_affect");
    expect(r.label).toBe("May Affect You");
  });

  it("the evaluation of one entry explains a failing condition in its own words", () => {
    const ev = evaluateEntry(E2, 1, { role: "renter", county: "Orange" });
    expect(ev.status).toBe("no");
    expect(ev.reason).toContain("Applies in Duval and Miami-Dade.");
    const ex = evaluateEntry(E1, 0, { role: "landlord", county: "Duval", property_type: "single_family" });
    expect(ex.reason).toContain("Not single-family homes.");
  });

  it("labels use Title Case", () => {
    expect(Object.values(RESULT_LABEL)).toEqual(["Applies to You", "May Affect You", "Text Is Ambiguous Here", "Can't Determine", "Does Not Appear to Apply", "Applies to Everyone"]);
  });
});

// Targeted requirement / exclusion / unknown-answer cases. The 40-entry audience
// baseline never exercised these (no requirement or exclusion was mapped).
describe("requirements and exclusions with unknown answers", () => {
  const nt = (attr: string, values: string[], from: CriterionTest["from"]): CriterionTest => ({ attr, op: "not_in", values, from });
  const one = (c: Criteria): LensBill => ({ entries: [entry("Landlords", c)], complete: true });
  const landlord = role("landlord");

  it("not_in on property type: a listed type is ruled out, any other type passes", () => {
    const bill = one(crit({ audience: landlord, requires: [nt("property_type", ["single_family"], { kind: "condition", index: 0 })] }));
    expect(label(bill, { role: "landlord", property_type: "single_family" })).toBe("Does Not Appear to Apply");
    expect(label(bill, { role: "landlord", property_type: "multifamily" })).toBe("Applies to You");
  });

  it("not_in on property type with no answer is unknown, and asks for it", () => {
    const bill = one(crit({ audience: landlord, requires: [nt("property_type", ["single_family"], { kind: "condition", index: 0 })] }));
    const r = matchBill(bill, { role: "landlord" });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual(["property_type"]);
  });

  it("not_in on jurisdiction: a reader in the listed county is out, elsewhere is in, no county is unknown", () => {
    const bill = one(crit({ audience: landlord, requires: [nt("jurisdiction", ["county:Duval"], { kind: "condition", index: 0 })] }));
    expect(label(bill, { role: "landlord", county: "Duval" })).toBe("Does Not Appear to Apply");
    expect(label(bill, { role: "landlord", county: "Leon" })).toBe("Applies to You");
    expect(matchBill(bill, { role: "landlord" }).result).toBe("cant_determine");
  });

  it("an exception that is unknown keeps a satisfied requirement from becoming Applies", () => {
    const bill = one(crit({ audience: landlord, requires: [req("jurisdiction", COVERED)], excludes: [exc("property_type", ["single_family"])] }));
    const r = matchBill(bill, { role: "landlord", county: "Duval" });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual(["property_type"]);
  });

  it("a holding exception rules the entry out even when a requirement is still unknown", () => {
    const bill = one(crit({ audience: landlord, requires: [req("jurisdiction", COVERED)], excludes: [exc("property_type", ["single_family"])] }));
    expect(label(bill, { role: "landlord", property_type: "single_family" })).toBe("Does Not Appear to Apply");
  });

  it("a requirement that names a county and a municipality is met by either", () => {
    const bill = one(crit({ audience: landlord, requires: [req("jurisdiction", ["county:Duval", "municipality:Miami"])] }));
    expect(label(bill, { role: "landlord", county: "Duval" })).toBe("Applies to You");
    expect(label(bill, { role: "landlord", county: "Broward", municipality: "Miami" })).toBe("Applies to You");
  });

  it("a county outside the list stays unknown while the municipality is unanswered", () => {
    const bill = one(crit({ audience: landlord, requires: [req("jurisdiction", ["county:Duval", "municipality:Miami"])] }));
    const r = matchBill(bill, { role: "landlord", county: "Broward" });
    expect(r.result).toBe("cant_determine");
    expect(r.ask).toEqual(["municipality"]);
  });

  it("an affected party is still tested against requirements", () => {
    const bill = one(crit({ audience: role("insurer"), affected: role("insured"), requires: [req("jurisdiction", COVERED)] }));
    expect(label(bill, { role: "insured", county: "Leon" })).toBe("Does Not Appear to Apply");
  });

  it("a mixed unknown and false requirement resolves to false", () => {
    const bill = one(crit({ audience: landlord, requires: [req("jurisdiction", COVERED, 0), req("property_type", ["multifamily"], 1)] }));
    expect(label(bill, { role: "landlord", property_type: "single_family" })).toBe("Does Not Appear to Apply");
  });
});
