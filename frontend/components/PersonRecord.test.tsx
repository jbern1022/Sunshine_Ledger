import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PersonRecord from "./PersonRecord";
import type { PersonBillItem, PersonVoteItem } from "@/lib/types";

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

const bills: PersonBillItem[] = Array.from({ length: 14 }, (_, i) => ({
  entity_id: `s${i}`,
  bill_number: `SB ${i}`,
  name: `Sponsored ${i}`,
  status: "Introduced",
  relationship_type: i % 2 ? "co_sponsor" : "sponsor",
  last_action_date: null,
  what_it_does: null,
  tags: i < 2 ? [housing] : [education],
}));

const voteLinks = () => screen.queryAllByRole("link", { name: /^HB / });
const billLinks = () => screen.queryAllByRole("link", { name: /^SB / });

describe("PersonRecord", () => {
  it("keeps the vote list collapsed until asked, with the counts always shown", async () => {
    render(<PersonRecord votes={votes} bills={[]} />);

    expect(screen.getByText("All recorded votes")).toBeInTheDocument();
    expect(voteLinks()).toHaveLength(0);

    const toggle = screen.getByRole("button", { name: "Show the 30 votes" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(voteLinks()).toHaveLength(25);
    await userEvent.click(screen.getByRole("button", { name: "Show more (5 more)" }));
    expect(voteLinks()).toHaveLength(30);

    await userEvent.click(screen.getByRole("button", { name: "Hide the votes" }));
    expect(voteLinks()).toHaveLength(0);
  });

  it("filters votes by topic and shows plain counts", async () => {
    render(<PersonRecord votes={votes} bills={[]} />);

    await userEvent.click(screen.getByRole("button", { name: "Housing 3" }));

    expect(screen.getByRole("button", { name: "Housing 3" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Recorded votes on bills tagged Housing")).toBeInTheDocument();
    expect(screen.getByText(/2 roll calls on 2 bills/)).toBeInTheDocument(); // committee: HB 0, HB 2
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Show the 3 votes" }));
    expect(voteLinks()).toHaveLength(3);
    expect(screen.getByRole("link", { name: "roll call ↗" })).toHaveAttribute("href", "https://legiscan.com/rc/0");
  });

  it("shows the first 10 sponsored bills, then all of them", async () => {
    render(<PersonRecord votes={[]} bills={bills} />);

    expect(screen.getByRole("heading", { name: "Sponsored and co-sponsored bills (14)" })).toBeInTheDocument();
    expect(billLinks()).toHaveLength(10);
    await userEvent.click(screen.getByRole("button", { name: "Show all 14" }));
    expect(billLinks()).toHaveLength(14);
  });

  it("filters the sponsored bills by the same topic as the votes", async () => {
    render(<PersonRecord votes={votes} bills={bills} />);

    await userEvent.click(screen.getByRole("button", { name: "Housing 3" }));

    expect(screen.getByRole("heading", { name: "Sponsored and co-sponsored bills tagged Housing (2)" })).toBeInTheDocument();
    expect(billLinks().map((l) => l.textContent)).toEqual(["SB 0", "SB 1"]);
    expect(screen.queryByRole("button", { name: /Show all/ })).not.toBeInTheDocument();
  });
});
