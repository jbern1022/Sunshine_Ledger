import { describe, expect, it } from "vitest";
import { displayStatus } from "./displayStatus";
import { applicability, effectiveLabel } from "./billStatus";

describe("displayStatus", () => {
  it("names the companion that replaced a tabled bill", () => {
    expect(displayStatus("Introduced", "Laid on Table, refer to CS/HB 1219")).toBe("Replaced by CS/HB 1219");
    expect(displayStatus("Engrossed", "Laid on Table, refer to CS/CS/SB 7002")).toBe("Replaced by CS/CS/SB 7002");
  });

  it.each([
    ["Adopted, companion bill(s) passed, see HR 8087 (Adopted)", "Replaced by HR 8087 (adopted)"],
    ["Adopted by Publication", "Adopted"],
    ["Died on Calendar", "Died"],
    ["Died on Second Reading Calendar", "Died"],
    ["Withdrawn prior to introduction", "Withdrawn"],
    ["Withdrawn from further consideration", "Withdrawn"],
    ["Laid on Table", "Tabled"],
  ])("reads the final action %s as %s", (action, label) => {
    expect(displayStatus("Introduced", action)).toBe(label);
  });

  it("leaves a live bill alone", () => {
    expect(displayStatus("Introduced", "Referred to Health Policy")).toBe("Introduced");
    expect(displayStatus("Introduced", null)).toBe("Introduced");
  });

  it("does not relabel an outcome", () => {
    expect(displayStatus("Passed", "Laid on Table, refer to CS/HB 1")).toBe("Passed");
  });

  it("puts clerk workflow words into reader words", () => {
    expect(displayStatus("Agenda Ready")).toBe("On an upcoming agenda");
    expect(displayStatus("Consent Agenda")).toBe("On a consent agenda");
    expect(displayStatus("Adopted")).toBe("Adopted");
  });

  it.each(["Died", "Tabled", "Withdrawn"])("%s reads like a bill that did not pass", (label) => {
    expect(effectiveLabel(label)).toBe("Would have taken effect");
  });

  it("a replaced bill reads like one that did not pass", () => {
    const s = displayStatus("Introduced", "Laid on Table, refer to CS/HB 1219");
    expect(effectiveLabel(s)).toBe("Would have taken effect");
    expect(applicability(s, null).verb).toBe("Would have applied to");
  });
});
