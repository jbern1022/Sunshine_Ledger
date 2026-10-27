import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import DataFreshness from "./DataFreshness";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({ fetchSourceStatus: vi.fn() }));

const nightly = (key: string, label: string, stale = false) => ({
  key,
  label,
  jurisdiction: null,
  schedule: "Nightly",
  note: "",
  last_checked_at: "2026-09-26T08:00:00Z",
  stale,
  bill_count: 1,
  bills_with_text: 1,
});

describe("DataFreshness", () => {
  it("says when bills were last checked and links to the source list", async () => {
    vi.mocked(api.fetchSourceStatus).mockResolvedValueOnce([nightly("legiscan", "Florida Legislature")]);
    render(<DataFreshness />);

    expect(await screen.findByText(/checked nightly · last checked Sep 26/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "About our data" })).toHaveAttribute("href", "/methodology#data-sources");
  });

  it("names stale sources", async () => {
    vi.mocked(api.fetchSourceStatus).mockResolvedValueOnce([
      nightly("legiscan", "Florida Legislature"),
      nightly("iqm2_miami", "City of Miami (iQM2)", true),
    ]);
    render(<DataFreshness />);

    expect(await screen.findByText(/Not updated on schedule: City of Miami \(iQM2\)/)).toBeInTheDocument();
  });

  it("says so when the status can't be fetched", async () => {
    vi.mocked(api.fetchSourceStatus).mockRejectedValueOnce(new Error("down"));
    render(<DataFreshness />);

    expect(await screen.findByText(/couldn't check how recently the data was updated/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "About our data" })).toBeInTheDocument();
  });

  it("does not claim a check date when a source has never been checked", async () => {
    vi.mocked(api.fetchSourceStatus).mockResolvedValueOnce([
      nightly("legiscan", "Florida Legislature"),
      { ...nightly("legistar_fortlauderdale", "Fort Lauderdale"), last_checked_at: null },
    ]);
    render(<DataFreshness />);

    expect(await screen.findByText(/no recorded update yet/)).toBeInTheDocument();
    expect(screen.queryByText(/last checked/)).not.toBeInTheDocument();
  });
});
