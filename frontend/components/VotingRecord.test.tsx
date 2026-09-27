import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import VotingRecord from "./VotingRecord";
import type { PersonVoteItem } from "@/lib/types";

const housing = { slug: "housing", label: "Housing" };
const education = { slug: "education", label: "Education" };

const votes: PersonVoteItem[] = Array.from({ length: 30 }, (_, i) => ({
  entity_id: `b${i}`,
  bill_number: `HB ${i}`,
  bill_name: `Bill ${i}`,
  vote: i === 0 ? "Nay" : "Yea",
  roll_call_description: i % 2 ? "House: Third Reading RCS#1" : "House Education Committee",
  date: "2026-03-04",
  roll_call_id: String(i),
  stage: i % 2 ? "floor" : "committee",
  source_url: i === 0 ? "https://legiscan.com/rc/0" : null,
  tags: i < 3 ? [housing] : [education],
}));

describe("VotingRecord", () => {
  it("filters by topic and shows plain counts", async () => {
    render(<VotingRecord votes={votes} bills={[]} />);

    expect(screen.getByText("All recorded votes")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /^HB / })).toHaveLength(25);

    await userEvent.click(screen.getByRole("button", { name: "Housing 3" }));

    expect(screen.getByRole("button", { name: "Housing 3" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Recorded votes on bills tagged Housing")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /^HB / })).toHaveLength(3);
    expect(screen.getByText(/2 roll calls on 2 bills/)).toBeInTheDocument(); // committee: HB 0, HB 2
    expect(screen.getByRole("link", { name: "roll call ↗" })).toHaveAttribute("href", "https://legiscan.com/rc/0");
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
  });

  it("pages through long records", async () => {
    render(<VotingRecord votes={votes} bills={[]} />);
    await userEvent.click(screen.getByRole("button", { name: "Show more (5 more)" }));
    expect(screen.getAllByRole("link", { name: /^HB / })).toHaveLength(30);
  });
});
