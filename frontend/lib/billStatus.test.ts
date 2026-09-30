import { describe, it, expect } from "vitest";
import { effectiveLabel } from "./billStatus";

describe("effectiveLabel", () => {
  it("matches the bill's fate", () => {
    expect(effectiveLabel("Passed")).toBe("Takes effect");
    expect(effectiveLabel("Adopted with Modification(s)")).toBe("Takes effect");
    expect(effectiveLabel("Vetoed")).toBe("Would have taken effect");
    expect(effectiveLabel("Introduced")).toBe("If enacted, takes effect");
    expect(effectiveLabel(null)).toBe("If enacted, takes effect");
  });
});
