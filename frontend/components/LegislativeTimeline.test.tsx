import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LegislativeTimeline from "./LegislativeTimeline";
import type { ActionOut, AmendmentOut, RollCallOut } from "@/lib/types";
import hb1389 from "@/lib/__fixtures__/hb1389.json";

const f = hb1389 as { actions: ActionOut[]; votes: RollCallOut[]; amendments: AmendmentOut[] };

describe("LegislativeTimeline", () => {
  it("shows key steps first and expands to the full history", async () => {
    render(<LegislativeTimeline actions={f.actions} votes={f.votes} amendments={f.amendments} officialUrl="https://example.com/hb1389" />);

    expect(screen.getByRole("heading", { name: "How it became law" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(12);
    expect(screen.getByText("Approved by Governor")).toBeInTheDocument();
    expect(screen.queryByText("1st Reading (Original Filed Version)")).not.toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "Show all 63 steps" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);

    expect(screen.getAllByRole("listitem")).toHaveLength(63);
    expect(screen.getAllByText("1st Reading (Original Filed Version)").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Show key steps only" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Official bill history ↗" })).toHaveAttribute("href", "https://example.com/hb1389");
  });

  it("titles a bill that didn't pass as legislative history", () => {
    render(
      <LegislativeTimeline
        actions={[
          { date: "2026-01-05", chamber: "Senate", action: "Filed", important: true },
          { date: "2026-03-13", chamber: "Senate", action: "Died in Rules", important: true },
        ]}
        votes={[]}
        amendments={[]}
        officialUrl={null}
      />,
    );
    expect(screen.getByRole("heading", { name: "Legislative history" })).toBeInTheDocument();
  });
});
