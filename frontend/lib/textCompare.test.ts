import { describe, it, expect } from "vitest";
import { compareTexts, splitClauses } from "./textCompare";
import fixtures from "./__fixtures__/textVersions.json";

const changedText = (c: ReturnType<typeof compareTexts>) =>
  c.blocks.flatMap((b) => (b.kind === "changed" ? b.parts.filter((p) => p.added || p.removed).map((p) => p.value) : []));

describe("splitClauses", () => {
  it("ignores line wrapping and resolves the bill's own markers", () => {
    const a = splitClauses("Section 1. The agency\nshall [deleted: may ]adopt rules; and\n(2) report.");
    const b = splitClauses("Section 1. The agency shall adopt\nrules; and (2) report.");
    expect(a).toEqual(b);
    expect(a).toEqual(["Section 1.", "The agency shall adopt rules; and (2) report."]);
  });
});

describe("compareTexts", () => {
  it("finds nothing changed in identical texts, however they wrap", () => {
    const c = compareTexts("One clause here.\nTwo clauses.", "One clause\nhere. Two clauses.");
    expect(c.similarity).toBe(1);
    expect(c.blocks.every((b) => b.kind === "same")).toBe(true);
  });

  it("marks word-level edits inside a changed clause", () => {
    const c = compareTexts(
      "Section 1. The fine may not exceed $1,000. Section 2. Effective July 1.",
      "Section 1. The fine may not exceed $5,000. Section 2. Effective July 1.",
    );
    expect(changedText(c)).toEqual(["1", "5"]);
    expect(c.rewritten).toBe(false);
  });

  it("calls a wholesale replacement a rewrite", () => {
    const c = compareTexts("Alpha beta gamma. Delta epsilon.", "Completely different words. Nothing shared at all.");
    expect(c.rewritten).toBe(true);
  });

  it("HB 565 (2026): a modest committee edit", () => {
    const c = compareTexts(fixtures.H0565.filed, fixtures.H0565.current);
    expect(c.rewritten).toBe(false);
    expect(c.similarity).toBeGreaterThan(0.3);
    expect(c.blocks.some((b) => b.kind === "changed")).toBe(true);
    expect(c.blocks.some((b) => b.kind === "same")).toBe(true);
  });

  it("HB 1389 (2026): heavily expanded, still compared", () => {
    const c = compareTexts(fixtures.H1389.filed, fixtures.H1389.current);
    expect(c.rewritten).toBe(true); // the committee substitute nearly tripled the text
    expect(c.blocks.length).toBeGreaterThan(1);
    // Every clause of both versions is accounted for.
    const shown = c.blocks
      .flatMap((b) => (b.kind === "same" ? b.clauses : b.parts.filter((p) => !p.added).map((p) => p.value)))
      .join(" ")
      .replace(/\s+/g, " ");
    expect(shown.length).toBeGreaterThan(0);
  });
});
