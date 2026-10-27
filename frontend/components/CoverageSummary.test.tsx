import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import CoverageSummary from "./CoverageSummary";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({ fetchSourceStatus: vi.fn() }));

const source = (key: string, jurisdiction: string | null, bill_count: number | null) => ({
  key,
  label: key,
  jurisdiction,
  schedule: "Nightly",
  note: "",
  last_checked_at: "2026-10-27T08:00:00Z",
  stale: false,
  bill_count,
  bills_with_text: bill_count,
});

describe("CoverageSummary", () => {
  it("counts the local governments that have records, not the state or non-bill sources", async () => {
    vi.mocked(api.fetchSourceStatus).mockResolvedValueOnce([
      source("legiscan", "FL", 3900),
      source("legistar_jaxcityc", "Jacksonville", 120),
      source("legistar_broward", "Broward County", 40),
      source("iqm2_miami", "Miami", 300),
      source("gdelt", null, null),
      source("census_bls", null, null),
    ]);
    render(<CoverageSummary />);

    expect(await screen.findByText(/Florida state bills plus 3 local governments/)).toBeInTheDocument();
    expect(screen.getByText(/does not mean it does not exist/)).toBeInTheDocument();
  });

  it("leaves out a registered local government that has no records yet", async () => {
    vi.mocked(api.fetchSourceStatus).mockResolvedValueOnce([
      source("legiscan", "FL", 3900),
      source("legistar_a", "A", 10),
      source("legistar_b", "B", 0),
    ]);
    render(<CoverageSummary />);

    expect(await screen.findByText(/Florida state bills plus 1 local government\b/)).toBeInTheDocument();
  });

  it("claims no number when the status cannot be loaded", async () => {
    vi.mocked(api.fetchSourceStatus).mockRejectedValueOnce(new Error("down"));
    render(<CoverageSummary />);

    expect(await screen.findByText(/Florida state bills plus a growing set of local governments/)).toBeInTheDocument();
    expect(screen.queryByText(/\d+ local governments?/)).not.toBeInTheDocument();
  });

  it("shows the number-free wording while loading", () => {
    vi.mocked(api.fetchSourceStatus).mockReturnValueOnce(new Promise(() => {}));
    render(<CoverageSummary />);

    expect(screen.getByText(/Florida state bills plus a growing set of local governments/)).toBeInTheDocument();
  });
});
