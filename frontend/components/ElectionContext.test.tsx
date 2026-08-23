import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import ElectionContext from "./ElectionContext";
import * as api from "@/lib/api";
import type { ElectionCalendar } from "@/lib/types";

vi.mock("@/lib/api", () => ({ fetchElections: vi.fn() }));

const calendar: ElectionCalendar = {
  state: "FL",
  year: 2026,
  source: {
    name: "Florida Department of State, Division of Elections",
    url: "https://dos.fl.gov/elections/for-voters/election-dates/",
  },
  verify_by: "2026-10-01",
  as_of: "2026-08-23",
  next_event: {
    date: "2026-10-05",
    label: "Voter registration deadline (General)",
    kind: "registration",
    is_past: false,
    days_away: 43,
  },
  events: [
    { date: "2026-08-18", label: "Primary Election", kind: "election", is_past: true, days_away: -5 },
    {
      date: "2026-10-05",
      label: "Voter registration deadline (General)",
      kind: "registration",
      is_past: false,
      days_away: 43,
    },
    { date: "2026-11-03", label: "General Election", kind: "election", is_past: false, days_away: 72 },
  ],
};

describe("ElectionContext", () => {
  beforeEach(() => vi.mocked(api.fetchElections).mockReset());

  it("shows the next upcoming date and credits the official source", async () => {
    vi.mocked(api.fetchElections).mockResolvedValueOnce(calendar);
    render(<ElectionContext />);

    expect(await screen.findByText(/Voter registration deadline \(General\)/)).toBeInTheDocument();
    expect(screen.getByText(/in 43 days/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Division of Elections/ })).toHaveAttribute(
      "href",
      "https://dos.fl.gov/elections/for-voters/election-dates/",
    );
  });

  it("states the non-claim explicitly", async () => {
    // BRD 5.8 permits the calendar but rules out scoring and prediction.
    // Putting an election date above a list of bills invites readers to
    // infer a link, so the disclaimer is load-bearing, not decoration.
    vi.mocked(api.fetchElections).mockResolvedValueOnce(calendar);
    render(<ElectionContext />);

    expect(
      await screen.findByText(/does not link bills to candidates, parties, or races/i),
    ).toBeInTheDocument();
  });

  it("renders nothing when the calendar can't be loaded", async () => {
    // Civic context is never a reason to break the page it sits above.
    vi.mocked(api.fetchElections).mockRejectedValueOnce(new Error("boom"));
    const { container } = render(<ElectionContext />);

    await waitFor(() => expect(api.fetchElections).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("does not present a finished election as upcoming", async () => {
    vi.mocked(api.fetchElections).mockResolvedValueOnce(calendar);
    render(<ElectionContext />);

    await screen.findByText(/Voter registration deadline \(General\)/);
    // The primary already happened; only the general should be surfaced.
    expect(screen.queryByText(/Primary Election/)).not.toBeInTheDocument();
    expect(screen.getByText(/General Election/)).toBeInTheDocument();
  });
});
