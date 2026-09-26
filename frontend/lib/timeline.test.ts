import { describe, it, expect } from "vitest";
import { becameLaw, buildTimeline, formatStepDate } from "./timeline";
import type { ActionOut, AmendmentOut, RollCallOut } from "./types";
import hb1389 from "./__fixtures__/hb1389.json";
import sb0002 from "./__fixtures__/sb0002.json";

type Fixture = { actions: ActionOut[]; votes: RollCallOut[]; amendments: AmendmentOut[] };
const build = (f: Fixture) => buildTimeline(f.actions, f.votes, f.amendments);

describe("buildTimeline (HB 1389, 2026: became law)", () => {
  const steps = build(hb1389 as Fixture);
  const key = steps.filter((s) => s.key);

  it("keeps every history step, every roll call and the adopted amendment", () => {
    expect(steps).toHaveLength(55 + 7 + 1);
  });

  it("reduces the key view to filing, votes, the adopted amendment and the outcome", () => {
    expect(key.map((s) => [s.date, s.kind, s.detail ?? s.text])).toEqual([
      ["2026-01-09", "filed", "Filed"],
      ["2026-02-11", "vote", "passed 15–0"],
      ["2026-02-18", "vote", "passed 13–2"],
      ["2026-02-24", "vote", "passed 18–5"],
      ["2026-03-04", "vote", "passed 76–29"],
      ["2026-03-06", "vote", "passed 34–0"],
      ["2026-03-12", "amendment", "adopted"],
      ["2026-03-12", "vote", "passed 98–4"],
      ["2026-03-13", "vote", "passed 35–0"],
      ["2026-06-15", "outcome", "Signed by Officers and presented to Governor"],
      ["2026-06-26", "outcome", "Approved by Governor"],
      ["2026-06-29", "outcome", key[11].text],
    ]);
    expect(key[11].text).toMatch(/^Chapter No\. 2026-179/);
  });

  it("links votes and amendments to their sections and names the chamber", () => {
    const vote = key.find((s) => s.kind === "vote")!;
    expect(vote.href).toMatch(/^#roll-call-/);
    expect(vote.chamber).toBe("House");
    expect(key.find((s) => s.kind === "amendment")!.href).toMatch(/^#amendment-/);
  });

  it("detects that it became law", () => {
    expect(becameLaw((hb1389 as Fixture).actions)).toBe(true);
  });
});

describe("buildTimeline (SB 2, 2026: died in committee)", () => {
  const steps = build(sb0002 as Fixture);

  it("ends on the death in committee and is not called law", () => {
    const key = steps.filter((s) => s.key);
    expect(key[0].kind).toBe("filed");
    expect(key[key.length - 1]).toMatchObject({ kind: "outcome" });
    expect(key[key.length - 1].text).toMatch(/^Died in /);
    expect(becameLaw((sb0002 as Fixture).actions)).toBe(false);
  });
});

describe("buildTimeline edge cases", () => {
  it("leaves out amendments that weren't adopted and treats referral withdrawals as ordinary steps", () => {
    const steps = buildTimeline(
      [
        { date: "2026-01-05", chamber: "Senate", action: "Filed", important: true },
        { date: "2026-02-01", chamber: "Senate", action: "Withdrawn from Rules", important: true },
      ],
      [],
      [{ id: "a1", amendment_id: 1, date: "2026-01-20", chamber: "Senate", adopted: false, description: "Amendment #1", amendment_text: null }],
    );
    expect(steps.map((s) => [s.kind, s.key])).toEqual([
      ["filed", true],
      ["action", false],
    ]);
  });

  it("formats calendar dates without shifting the day", () => {
    expect(formatStepDate("2026-01-09")).toBe("Jan 9");
  });
});

describe("committee substitutes", () => {
  it("doesn't treat a bill laid on the table for its committee substitute as an outcome", () => {
    const steps = buildTimeline(
      [{ date: "2026-02-12", chamber: "House", action: "Laid on Table under Rule 7.18(a)", important: true }],
      [],
      [],
    );
    expect(steps[0]).toMatchObject({ kind: "action", key: false });
  });
});
