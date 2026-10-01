import { describe, it, expect } from "vitest";
import { applicability, effectiveLabel } from "./billStatus";

describe("effectiveLabel", () => {
  it("matches the bill's fate", () => {
    expect(effectiveLabel("Passed")).toBe("Takes effect");
    expect(effectiveLabel("Adopted with Modification(s)")).toBe("Takes effect");
    expect(effectiveLabel("Vetoed")).toBe("Would have taken effect");
    expect(effectiveLabel("Introduced")).toBe("If enacted, takes effect");
    expect(effectiveLabel(null)).toBe("If enacted, takes effect");
  });
});

describe("applicability", () => {
  const today = new Date("2026-10-01T12:00:00Z");
  const july2027 = { when: "July 1, 2027", has_exceptions: false };

  it("follows the bill's status", () => {
    expect(applicability("Introduced", july2027, today)).toEqual({ verb: "Would apply to", note: "if enacted" });
    expect(applicability("Vetoed", july2027, today).verb).toBe("Would have applied to");
    expect(applicability("Failed", null, today).verb).toBe("Would have applied to");
  });

  it("separates enacted-not-yet-effective from effective", () => {
    expect(applicability("Passed", july2027, today).verb).toBe("Will apply beginning July 1, 2027 to");
    expect(applicability("Passed", { when: "July 1, 2026", has_exceptions: false }, today).verb).toBe("Applies to");
    expect(applicability("Adopted", { when: "upon signature by the Council President", has_exceptions: false }, today).verb)
      .toBe("Applies to");
  });

  it("keeps unknown or phased starts explicit", () => {
    expect(applicability("Passed", null, today)).toEqual({
      verb: "Applies once in effect to",
      note: "The bill text doesn't state when it takes effect.",
    });
    expect(applicability("Passed", { when: "July 1, 2026", has_exceptions: true }, today).note).toMatch(/own dates/);
    expect(applicability("Passed", { when: "on the date the department certifies", has_exceptions: false }, today))
      .toEqual({ verb: "Applies once in effect to", note: "Takes effect on the date the department certifies, per the bill text." });
  });
});
