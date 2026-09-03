import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PeoplePage from "./page";
import * as api from "@/lib/api";
import type { PersonListItem } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  fetchPeople: vi.fn(),
}));

function makePerson(entity_id: string, overrides: Partial<PersonListItem> = {}): PersonListItem {
  return {
    entity_id,
    name: `Person ${entity_id}`,
    district: "District 5",
    role: "Representative",
    party: "N/A",
    jurisdiction_name: "FL",
    sponsored_count: 3,
    ...overrides,
  };
}

describe("PeoplePage", () => {
  beforeEach(() => {
    vi.mocked(api.fetchPeople).mockReset();
  });

  it("shows a loading state before the first response arrives", () => {
    vi.mocked(api.fetchPeople).mockReturnValueOnce(new Promise(() => {}));
    render(<PeoplePage />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows an error message when the fetch fails", async () => {
    vi.mocked(api.fetchPeople).mockRejectedValueOnce(new Error("network error"));
    render(<PeoplePage />);
    expect(await screen.findByText(/couldn.t load legislators/i)).toBeInTheDocument();
  });

  it("shows an empty-state message when no sponsors match", async () => {
    vi.mocked(api.fetchPeople).mockResolvedValueOnce({ total: 0, items: [] });
    render(<PeoplePage />);
    expect(await screen.findByText(/no sponsors match that search/i)).toBeInTheDocument();
  });

  it("renders sponsors with their role/district/party and a correctly pluralized bill count", async () => {
    vi.mocked(api.fetchPeople).mockResolvedValueOnce({
      total: 2,
      items: [
        makePerson("p1", { sponsored_count: 1 }),
        makePerson("p2", { role: null, district: null, party: null, sponsored_count: 4 }),
      ],
    });
    render(<PeoplePage />);

    expect(await screen.findByText("Person p1")).toBeInTheDocument();
    expect(screen.getByText("Representative · District 5 · N/A")).toBeInTheDocument();
    expect(screen.getByText("1 bill")).toBeInTheDocument();
    expect(screen.getByText("4 bills")).toBeInTheDocument();
    expect(screen.getByText("2 sponsors")).toBeInTheDocument();
  });

  it("re-fetches with the search text as the user types", async () => {
    vi.mocked(api.fetchPeople).mockResolvedValue({ total: 0, items: [] });
    const user = userEvent.setup();
    render(<PeoplePage />);

    await waitFor(() => expect(api.fetchPeople).toHaveBeenCalledWith({ q: undefined, limit: 100 }));

    await user.type(screen.getByLabelText(/search sponsors/i), "Smith");

    await waitFor(() =>
      expect(api.fetchPeople).toHaveBeenLastCalledWith({ q: "Smith", limit: 100 }),
    );
  });

  it("does not let a slower, stale response overwrite a newer one", async () => {
    // Real race condition this component guards against via its `cancelled`
    // flag: if the query changes again before the first request resolves,
    // that first (now-stale) response must not clobber the second one.
    let resolveFirst!: (value: { total: number; items: PersonListItem[] }) => void;
    const firstCall = new Promise<{ total: number; items: PersonListItem[] }>((resolve) => {
      resolveFirst = resolve;
    });

    vi.mocked(api.fetchPeople)
      .mockReturnValueOnce(firstCall)
      .mockResolvedValueOnce({ total: 1, items: [makePerson("fresh")] });

    const user = userEvent.setup();
    render(<PeoplePage />);

    await user.type(screen.getByLabelText(/search sponsors/i), "a");
    await screen.findByText("Person fresh");

    // The slow first request finally resolves after the second one already
    // rendered -- its stale data must not appear.
    resolveFirst({ total: 1, items: [makePerson("stale")] });
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByText("Person fresh")).toBeInTheDocument();
    expect(screen.queryByText("Person stale")).not.toBeInTheDocument();
  });
});
