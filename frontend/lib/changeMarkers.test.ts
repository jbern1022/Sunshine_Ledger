import { describe, it, expect } from "vitest";
import { lawAsAmended, parseChangeMarkers } from "./changeMarkers";

describe("parseChangeMarkers", () => {
  it("returns a single text segment when there are no markers", () => {
    expect(parseChangeMarkers("Section 1. Plain text.")).toEqual([
      { kind: "text", text: "Section 1. Plain text." },
    ]);
  });

  it("splits deleted and added markers out in order", () => {
    expect(parseChangeMarkers("An [deleted: No] agency or [added: a] state official")).toEqual([
      { kind: "text", text: "An " },
      { kind: "deleted", text: "No" },
      { kind: "text", text: " agency or " },
      { kind: "added", text: "a" },
      { kind: "text", text: " state official" },
    ]);
  });

  it("handles adjacent markers with no text between them", () => {
    expect(parseChangeMarkers("[added: 2.][deleted: 1.] Section 379.354")).toEqual([
      { kind: "added", text: "2." },
      { kind: "deleted", text: "1." },
      { kind: "text", text: " Section 379.354" },
    ]);
  });

  it("treats a marker cut off at the end as a marker, not plain text", () => {
    expect(parseChangeMarkers("keep [deleted: trunc")).toEqual([
      { kind: "text", text: "keep " },
      { kind: "deleted", text: "trunc" },
    ]);
  });

  it("returns nothing for empty text", () => {
    expect(parseChangeMarkers("")).toEqual([]);
  });
});

describe("lawAsAmended", () => {
  it("drops deleted wording and unwraps added wording", () => {
    expect(lawAsAmended("An [deleted: No] agency or [added: a] state official")).toBe(
      "An agency or a state official",
    );
  });

  it("drops the space a deletion leaves before punctuation", () => {
    expect(lawAsAmended("managers [deleted: and supervisors], and staff")).toBe("managers, and staff");
  });

  it("reads a glued renumbering as the new number only", () => {
    expect(lawAsAmended("[added: 2.][deleted: 1.] Section 379.354(16)")).toBe("2. Section 379.354(16)");
  });

  it("keeps line structure", () => {
    expect(lawAsAmended("Section 1. [added: New.]\nSection 2. [deleted: Old.] Kept.")).toBe(
      "Section 1. New.\nSection 2. Kept.",
    );
  });

  it("handles truncated markers", () => {
    expect(lawAsAmended("keep [deleted: gone")).toBe("keep");
    expect(lawAsAmended("keep [added: new")).toBe("keep new");
  });

  it("leaves text without markers unchanged", () => {
    const text = "Foo , bar ; baz. Section 2. More.";
    expect(lawAsAmended(text)).toBe(text);
  });
});
